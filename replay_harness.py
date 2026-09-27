"""
Replay harness — measures a mapping table + schema against real OLIS histories.

The point is not to replay one bill. It is to make every change to the rules or
the schema produce a NUMBER you can compare against the last run:

    bills replayed / bills completed / halt reasons ranked / unmatched text ranked

Run it before and after any rule edit. If completed goes down, you regressed.

Usage:
    python replay_harness.py --session 2025R1 --limit 200
    python replay_harness.py --session 2025R1 --measures SB976,HB2001

No API key required. Oregon's OData service pages at 5000 rows; we filter
per-measure so paging is not usually needed.
"""

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

API = "https://api.oregonlegislature.gov/odata/odataservice.svc"


# --------------------------------------------------------------------------
# source
# --------------------------------------------------------------------------

def odata(entity: str, filt: str, select: str | None = None, top: int | None = None,
          skip: int | None = None) -> list[dict]:
    params = {"$filter": filt, "$format": "json"}
    if select:
        params["$select"] = select
    if top:
        params["$top"] = str(top)
    if skip:
        params["$skip"] = str(skip)
    url = f"{API}/{entity}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read())["value"]


def measure_history(session: str, prefix: str, number: int) -> list[dict]:
    rows = odata(
        "MeasureHistoryActions",
        f"SessionKey eq '{session}' and MeasurePrefix eq '{prefix}' and MeasureNumber eq {number}",
    )
    # ActionDate is the only defensible sort key: MeasureHistoryId contradicts it
    # (observed: id 654676 @08:33 precedes id 654677 @08:32 in SB976 2025R1).
    rows.sort(key=lambda r: (r["ActionDate"], r["MeasureHistoryId"]))
    return rows


def session_measures(session: str, limit: int) -> list[tuple[str, int]]:
    rows = odata("Measures", f"SessionKey eq '{session}'",
                 select="MeasurePrefix,MeasureNumber", top=limit)
    return [(r["MeasurePrefix"], r["MeasureNumber"]) for r in rows]


# --------------------------------------------------------------------------
# mapping — REPLACE THIS. it is the thing under test.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Emit:
    state: Optional[str]
    payload: dict
    rule_id: str
    span: tuple[int, int]          # character offsets in the source row
    text: str                       # exact matched substring


# (rule_id, pattern, state_or_None, payload)
RULES: list[tuple[str, str, Optional[str], dict]] = [
    # --- introduction -----------------------------------------------------
    ("introduction_first_reading", r"Introduction and first reading",   "introduced", {}),
    ("measure_introduced",         r"measure introduced",               "introduced", {}),
    ("first_reading",              r"First reading",                    "introduced", {}),

    # --- referral ---------------------------------------------------------
    ("referred_to",                r"[Rr]eferred to ([^.]+)",           "committee", {"committee": r"\1"}),
    ("assigned_subcommittee",      r"Assigned to ([^.]+)",              "committee", {"subcommittee": r"\1"}),
    ("returned_full_committee",    r"Returned to Full Committee",       "committee", {"subcommittee": None}),
    ("returned_presidents_desk",   r"returned to President's desk",     "committee", {}),

    # --- committee events -------------------------------------------------
    # combined form is 34x more common than you would guess; must outrank the singles
    ("hearing_and_work_session",   r"Public Hearing and Work Session held", "work_session", {}),
    ("public_hearing_held",        r"Public Hearing held",              "public_hearing", {}),
    ("work_session_held",          r"Work Session held",                "work_session", {}),
    ("meeting_cancelled",          r"(Public Hearing|Work Session|Informational Meeting)[^.]*[Cc]ancelled",
                                                                        None, {"cancelled": True}),
    ("informational_meeting",      r"Informational Meeting held",       None, {}),
    ("event_not_held",              r"(Public Hearing|Work Session|Possible [^.]*) not held", None, {}),
    ("event_scheduled",             r"(Public Hearing|Work Session|Informational Meeting) [Ss]cheduled", None, {}),
    ("event_not_held",              r"(Public Hearing|Work Session|Possible [^.]*) not held", None, {}),
    ("event_scheduled",             r"(Public Hearing|Work Session|Informational Meeting) [Ss]cheduled", None, {}),
    ("event_not_held",              r"(Public Hearing|Work Session|Possible [^.]*) not held", None, {}),
    ("event_scheduled",             r"(Public Hearing|Work Session|Informational Meeting) [Ss]cheduled", None, {}),
    ("event_not_held",              r"(Public Hearing|Work Session|Possible [^.]*) not held", None, {}),
    ("event_scheduled",             r"(Public Hearing|Work Session|Informational Meeting) [Ss]cheduled", None, {}),
    ("in_committee_adjournment",   r"In committee upon adjournment",    "committee", {}),
    ("in_conference_adjournment",   r"In conference committee upon adjournment", "committee", {"conference": True}),
    ("in_conference_adjournment",   r"In conference committee upon adjournment", "committee", {"conference": True}),
    ("in_conference_adjournment",   r"In conference committee upon adjournment", "committee", {"conference": True}),
    ("in_conference_adjournment",   r"In conference committee upon adjournment", "committee", {"conference": True}),

    # --- recommendations --------------------------------------------------
    ("rec_do_pass",                r"Recomme[nd]dation:\s+Do pass",          "committee", {"recommendation": "do_pass"}),
    ("rec_do_adopt",               r"Recomme[nd]dation:\s+Do adopt",         "committee", {"recommendation": "do_adopt"}),
    ("rec_be_adopted",             r"Recomme[nd]dation:\s+Be adopted",       "committee", {"recommendation": "be_adopted"}),
    ("rec_none",                   r"Without recommendation",
                                                                        "committee", {"recommendation": "none"}),
    ("with_amendments",            r"with amendments",                  None, {"amended": True}),
    ("printed_engrossed",          r"printed ([A-Z])-Engrossed",        None, {"engrossment": r"\1"}),
    ("printed_eng_paren",          r"\(Printed ([A-Z])-Eng\.\)",        None, {"engrossment": r"\1"}),

    # --- floor ------------------------------------------------------------
    ("second_reading",             r"Second reading",                   "second_reading", {}),
    ("third_reading",              r"Third reading",                    "third_reading", {}),
    ("read",                       r"\bRead\b(?! as)",                  "third_reading", {}),
    ("final_reading",              r"Final reading",                    "third_reading", {}),
    ("special_order",              r"(Made a?|Motion to make a?) Special Order of Business( on [^.]*)?",
                                                                        None, {"special_order": True}),
    ("taken_from_calendar",        r"Taken from [^.]*Calendar[^.]*",    None, {"recalendared": True}),
    ("placed_on_calendar",         r"[Pp]laced on [^.]*Calendar[^.]*",  None, {"recalendared": True}),
    ("read_special_order",         r"Read as Special Order of Business", "third_reading", {}),
    # "Motion to suspend the rules passed." is the motion passing, not the measure.
    # (HB2341, HB2360, 2021R1)
    ("motion_suspend_passed",      r"Motion to suspend the rules passed", None, {"rules_suspended": True}),
    ("passed",                     r"\bPassed\b",                       "passed", {}),
    ("adopted_cc_report",          r"(Senate|House) adopted Conference Committee Report[^.]*", "passed", {"conference": True}),
    ("repassed",                   r"[Rr]epassed( bill)?",              "passed", {"repassed": True}),
    ("not_concurring_paren",       r"\(Not concurring:[^)]+\)", None, {}),
    ("concurred",                  r"concurred in ([A-Za-z]+) amendments", None, {"concurred": True}),
    ("motion_failed",              r"Motion to [^.]*failed",            None, {"motion_failed": True}),
    ("motion_carried_refer",       r"Motion to r?e?refer to ([^.]+) carried[^.]*", "committee", {"committee": r"\1"}),
    ("motion_postpone",            r"Motion to pos[tp]one[^.]*",         None, {"postponed": True}),
    ("motion_postpone",            r"Motion to pos[tp]one[^.]*",         None, {"postponed": True}),
    ("motion_postpone",            r"Motion to pos[tp]one[^.]*",         None, {"postponed": True}),
    ("motion_postpone",            r"Motion to pos[tp]one[^.]*",         None, {"postponed": True}),
    ("motion_carried_generic",     r"Motion to [^.]*carried[^.]*",      None, {"motion_carried": True}),
    # "Motion to take and place ... Motion failed." -- a failed motion, not a failed
    # measure. Longest match beats "failed". (SB554, 2021R1)
    ("motion_failed_bare",         r"Motion failed",                    None, {"motion_failed": True}),
    ("failed",                     r"\bFailed\b",                       "failed", {}),
    ("refused_to_concur",          r"(House|Senate) refused to concur[^.]*", "committee", {"concurrence": "refused"}),
    ("adopted",                    r"\bAdopted\b",                      "adopted", {}),
    ("rules_suspended",            r"Rules suspended",                  None, {"rules_suspended": True}),
    ("carried_by",                 r"Carried by ([^.]+)",               None, {"carried_by": r"\1"}),
    ("carried_over",               r"Carried [Oo]ver to [^.]+",         None, {"carried_over": True}),
    ("vote_explanation",           r"Vote explanation[^.]*",  None, {}),
    ("motion_to_table",            r"Motion to lay bill.*on the table", "tabled", {}),
    ("withdrawn_committee",        r"[Ww]ithdrawn from committee",      "committee", {}),

    # --- executive / post-passage ----------------------------------------
    ("president_signed",           r"President signed",                 "signed_by_presiding", {"signer": "president"}),
    ("speaker_signed",             r"Speaker signed",                   "signed_by_presiding", {"signer": "speaker"}),
    # Signed into law with some items struck. The measure is enacted; a later "Veto
    # sustained" row concerns the struck items, not the measure (see step()).
    ("governor_signed_line_item",  r"Governor signed with line-item veto", "enacted_line_item_veto",
                                                                        {"veto_type": "line_item"}),
    ("governor_signed",            r"Governor signed",                  "enacted", {}),
    ("art_v_time_allowed",         r"The time allowed by Article V[^.]*", None, {}),
    ("art_v_time_allowed",         r"The time allowed by Article V[^.]*", None, {}),
    ("line_item_veto",             r"Governor purported to sign with line-item veto", "vetoed", {"veto_type": "line_item"}),
    ("governor_vetoed",            r"Governor vetoed",                  "vetoed", {}),
    ("veto_sustained",             r"Veto sustained[^.]*",              "veto_sustained", {}),
    ("veto_overridden",            r"Veto overridden[^.]*",             "veto_overridden", {}),
    ("repass_notwithstanding",     r"[Mm]otion to repass bill notwithstanding[^.]*veto carried[^.]*",
                                                                        "veto_overridden", {"override": True}),
    ("filed_sos",                  r"Filed with Secretary of State",    None, {"filed_sos": True}),
    ("chapter_number",             r"Chapter (\d+)[^.]*Laws",            None, {"chapter": r"\1"}),
    ("filed_without_signature", r"Filed without Governor.s signature", "enacted", {}),
    ("filed_without_signature", r"Filed without Governor.s signature", "enacted", {}),
    ("filed_without_signature", r"Filed without Governor.s signature", "enacted", {}),
    ("filed_without_signature", r"Filed without Governor.s signature", "enacted", {}),
    ("effective_date",             r"Effective date[^.]*",              None, {}),
    ("effective_91st_day",         r"[Ee]ffective on the \d+\w* day[^.]*", None, {}),
    ("subsequent_referral_denied", r"[Rr]escind[^.]*subsequent referral[^.]*denied[^.]*", None, {}),
    ("referral_rescinded_reref",    r"[Rr]eferral rescinded by order[^.]*", "committee", {}),
    ("subseq_referral_resc_denied", r"[Ss]ubsequent referral rescission denied[^.]*", None, {}),
    ("subsequent_referral_denied", r"[Rr]escind[^.]*subsequent referral[^.]*denied[^.]*", None, {}),
    ("referral_rescinded_reref",    r"[Rr]eferral rescinded by order[^.]*", "committee", {}),
    ("subseq_referral_resc_denied", r"[Ss]ubsequent referral rescission denied[^.]*", None, {}),
    ("subsequent_referral_denied", r"[Rr]escind[^.]*subsequent referral[^.]*denied[^.]*", None, {}),
    ("referral_rescinded_reref",    r"[Rr]eferral rescinded by order[^.]*", "committee", {}),
    ("subseq_referral_resc_denied", r"[Ss]ubsequent referral rescission denied[^.]*", None, {}),
    ("subsequent_referral_denied", r"[Rr]escind[^.]*subsequent referral[^.]*denied[^.]*", None, {}),
    ("referral_rescinded_reref",    r"[Rr]eferral rescinded by order[^.]*", "committee", {}),
    ("subseq_referral_resc_denied", r"[Ss]ubsequent referral rescission denied[^.]*", None, {}),
    ("subsequent_referral_resc",   r"[Ss]ubsequent referral[^.]*rescinded[^.]*", None, {"subsequent_referral": "rescinded"}),
    ("amendments_distributed",     r"\(Amendments distributed\.?\)",     None, {}),
    ("at_desk_adjournment",        r"At ((President's|Speaker's) desk|Desk) upon adjournment", None, {"location": "desk"}),
    ("governors_message_read",     r"Governor's message read[^.]*",     None, {}),
    # Appointing conferees puts the measure in conference committee for that chamber.
    # Recording it as a state is what lets a later "failed to adopt Conference Committee
    # Report" fail the measure without a passed -> failed edge. (HB3242, 2023R1)
    ("conferees_appointed",        r"[^.]*(appointed|discharged) (as )?(House|Senate) conferee[s]?[^.]*", "committee", {"conference": True}),
    ("conference_recommendation",  r"Conference Committee Recommendation:[^.]*", "committee", {"conference": True}),
    ("conference_report_dist",     r"Conference Committee Report distributed[^.]*", None, {"conference": True}),
    # Reading the conference report into the record is not a third reading of the bill;
    # the chamber's state is where its own last vote left it. (HB2312, HB2841, 2019R1)
    ("conference_report_read",     r"Conference Committee Report read in (Senate|House)", None, {"conference": True}),
    ("vote_reconsideration",       r"Vote reconsideration (carried|failed)",      None, {"reconsidered": True}),
    ("rereferred_bare",            r"\bRereferred\b",                   "committee", {}),
    ("notice_reconsideration",     r"[^.]*reconsideration[^.]*", None, {}),
    ("consent_change_vote",        r"[^.]*granted unanimous consent to change vote[^.]*", None, {}),
    ("tabled_simple",              r"\bTabled\b",                       "tabled", {}),
    ("veto_message_journal",       r"Governor's veto message entered into Journal", None, {}),
    ("conflict_declared",          r"[^.]*conflict[^.]*of interest[^.]*", None, {}),
    ("conflict_declared_alt",      r"[^.]*declared potential conflict of interest", None, {}),
    ("excused_vote",               r"[^.]*(excused|absent)[^.]*granted unanim[oa]+us consent to[^.]*", None, {}),
    ("vote_changed",               r"[^.]*changed from (aye|nay) to (aye|nay)[^.]*", None, {}),
    ("eng_base_ref",               r"(to )?the ([A-Z])-Eng\.? (bill|resolution|measure)", None, {}),
    ("referred_bare",              r"\bReferred\b(?! to)",              "committee", {}),
    ("special_order_bare",         r"(as )?a? ?Special Order of Business,?", None, {"special_order": True}),
    ("minority_report",            r"Minority Report[^.]*",              None, {"minority_report": True}),
    ("art_v_citation",             r"Art\. V, sec\. \d+\w*, Oregon Constitution", None, {}),
    ("and_be",                     r"\band be\b",                       None, {}),

    # --- organizational boilerplate (no procedural meaning) ---------------
    ("permanent_org_report",       r"Under the provisions of the Report[^.]*", None, {}),
    ("special_rules_report",       r"In com[np]liance with the Report[^.]*",   None, {}),
]


COMPILED = [(rid, re.compile(pat, re.IGNORECASE), st, pl) for rid, pat, st, pl in RULES]


def parse_row(action_text: str) -> tuple[list[Emit], list[str]]:
    """Span-based, no sentence splitting.

    Legal citations ("Art. V, sec. 15b") and legislator initials ("Smith G.")
    both contain periods, so splitting on them destroys the exact rows that
    matter. Instead: find every match over the FULL string, resolve overlaps by
    longest-match-wins, emit in offset order. Ordering falls out for free and
    each emit carries its character span for provenance.

    Returns (emits, uncovered_text_fragments).
    """
    hits = []
    for rid, rx, state, payload in COMPILED:
        for m in rx.finditer(action_text):
            hits.append((m.start(), m.end(), rid, state, payload, m))

    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    chosen, occupied = [], []
    for h in hits:
        if any(not (h[1] <= s or h[0] >= e) for s, e in occupied):
            continue
        occupied.append((h[0], h[1]))
        chosen.append(h)
    chosen.sort(key=lambda h: h[0])

    emits = []
    for start, end, rid, state, payload, m in chosen:
        resolved = {}
        for k, v in payload.items():
            if isinstance(v, str) and v.startswith("\\1") and m.groups():
                resolved[k] = m.group(1).strip()
            else:
                resolved[k] = v
        emits.append(Emit(state, resolved, rid, (start, end), m.group(0)))

    # whatever no rule claimed, minus punctuation/whitespace
    covered = bytearray(len(action_text))
    for s, e in occupied:
        for i in range(s, e):
            covered[i] = 1
    gaps, cur = [], ""
    for i, ch in enumerate(action_text):
        if covered[i]:
            if cur.strip(" .,;"):
                gaps.append(cur.strip(" .,;"))
            cur = ""
        else:
            cur += ch
    if cur.strip(" .,;"):
        gaps.append(cur.strip(" .,;"))
    return emits, gaps


# --------------------------------------------------------------------------
# schema — chamber-aware WITH a crossover edge (the piece that was missing)
# --------------------------------------------------------------------------

CHAMBER_FLOW = {
    # None -> third_reading exists for one measure, HCR21 (2021R1), whose first Senate
    # row is "Final reading ... Adopted." It does not move swap rejection; mapping
    # final_reading to no state instead cost ~200 resolutions (tried 2026-09-26).
    None: {"introduced", "adopted", "third_reading"},
    "introduced": {"committee", "second_reading", "third_reading", "adopted"},
    "committee": {"committee", "public_hearing", "work_session", "second_reading", "third_reading",
                  "passed", "adopted", "failed", "tabled", "signed_by_presiding"},
    "public_hearing": {"committee", "public_hearing", "work_session",
                       "second_reading", "third_reading"},
    "work_session": {"committee", "work_session", "public_hearing",
                     "second_reading", "third_reading"},
    "second_reading": {"third_reading", "committee", "failed"},
    "third_reading": {"passed", "adopted", "failed", "committee", "third_reading", "second_reading"},
    "passed": {"signed_by_presiding", "passed", "committee", "third_reading", "tabled",
               "adopted", "veto_sustained", "veto_overridden"},
    "adopted": {"signed_by_presiding", "committee", "adopted", "third_reading", "passed"},
    "failed": {"committee", "failed", "second_reading", "third_reading", "passed", "adopted"},
    "signed_by_presiding": {"signed_by_presiding", "enacted", "enacted_line_item_veto", "vetoed", "committee"},
    # Enacted is final for the measure. The four duplicated `"enacted": {"vetoed",
    # "veto_sustained"}` keys that stood here existed only to let HB5050 (2019R1) and
    # SB5506 (2023R1) replay, which recorded two enacted laws as vetoed. Both were
    # line-item vetoes; that path is modelled below instead.
    "enacted": set(),
    "enacted_line_item_veto": {"line_item_veto_sustained"},
    "vetoed": {"tabled", "veto_sustained", "veto_overridden", "committee", "passed"},
    "tabled": {"veto_sustained", "veto_overridden"},
}
TERMINAL = {"veto_sustained", "veto_overridden", "line_item_veto_sustained"}

# After a line-item veto the measure is law. OLIS records the Legislature declining to
# override the struck items with the same text as a full veto ("Veto sustained in
# accordance with Art. V, sec. 15b"), so the row is read by where the measure stands:
# from enacted_line_item_veto it means the item veto stood, not that the measure died.
CONTEXTUAL_STATE = {
    ("enacted_line_item_veto", "veto_sustained"): "line_item_veto_sustained",
}


class Halt(Exception):
    pass


@dataclass
class Item:
    id: str
    chamber: Optional[str] = None
    # per-chamber position; a measure has a state in EACH chamber, not one global state
    states: dict = field(default_factory=dict)
    payload: dict = field(default_factory=dict)
    history: list = field(default_factory=list)

    @property
    def state(self):
        return self.states.get(self.chamber)


def step(item: Item, to_state: str, chamber: str, occurred_at: str, rule_id: str, payload: dict):
    frm = item.states.get(chamber)
    to_state = CONTEXTUAL_STATE.get((frm, to_state), to_state)
    # crossover: origin chamber passed -> second chamber introduction is legal
    if frm is None and to_state == "introduced":
        pass
    elif frm not in CHAMBER_FLOW:
        raise Halt(f"unknown from_state {frm!r} in {chamber}")
    elif to_state not in CHAMBER_FLOW[frm]:
        raise Halt(f"{chamber}: {frm} -> {to_state} not allowed")
    if frm in TERMINAL:
        raise Halt(f"{chamber}: cannot leave terminal {frm}")
    item.states[chamber] = to_state
    item.chamber = chamber
    item.payload.update(payload)
    item.history.append((occurred_at, chamber, frm, to_state, rule_id))


def replay(measure_id: str, rows: list[dict]):
    item = Item(measure_id)
    uncovered = []
    for r in rows:
        emits, gaps = parse_row(r["ActionText"])
        uncovered.extend(gaps)
        if not emits:
            return item, f"NO RULE MATCHED: {r['ActionText'][:70]}", uncovered
        for e in emits:
            if e.state is None:
                item.payload.update(e.payload)
                continue
            try:
                step(item, e.state, r["Chamber"], r["ActionDate"], e.rule_id, e.payload)
            except Halt as h:
                return item, f"{h}  [rule={e.rule_id} row={r['ActionText'][:60]!r}]", uncovered
    return item, None, uncovered


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="2025R1")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--measures", help="comma list e.g. SB976,HB2001")
    args = ap.parse_args()

    if args.measures:
        targets = []
        for m in args.measures.split(","):
            m = m.strip()
            targets.append((re.match(r"[A-Za-z]+", m).group(0).upper(),
                            int(re.search(r"\d+", m).group(0))))
    else:
        targets = session_measures(args.session, args.limit)

    completed, halts, uncovered = 0, Counter(), Counter()
    finals = Counter()
    for prefix, number in targets:
        mid = f"{prefix}{number}"
        try:
            rows = measure_history(args.session, prefix, number)
        except Exception as exc:
            halts[f"FETCH FAILED: {type(exc).__name__}"] += 1
            continue
        if not rows:
            continue
        item, halt, gaps = replay(mid, rows)
        uncovered.update(g for g in gaps if len(g) > 3)
        if halt:
            halts[halt.split("  [")[0]] += 1
        else:
            completed += 1
            finals[str(item.states)] += 1

    total = len(targets)
    print(f"session={args.session}  measures={total}  completed={completed} "
          f"({100*completed/max(total,1):.1f}%)\n")
    print("--- halt reasons (ranked) ---")
    for reason, n in halts.most_common(20):
        print(f"{n:5}  {reason}")
    print("\n--- uncovered text fragments (ranked) ---")
    for frag, n in uncovered.most_common(25):
        print(f"{n:5}  {frag[:78]}")
    print("\n--- final states of completed replays ---")
    for st, n in finals.most_common(10):
        print(f"{n:5}  {st}")


if __name__ == "__main__":
    main()
