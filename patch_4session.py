import os
os.chdir(os.path.expanduser('~/proc_track'))
src = open('replay_harness.py').read()

# 1. "not held" events
src = src.replace(
    '("event_scheduled",',
    '("event_not_held",              r"(Public Hearing|Work Session|Possible [^.]*) not held", None, {}),\n    ("event_scheduled",')

# 2. Rescission denied (all spelling variants)
src = src.replace(
    '("subsequent_referral_denied", r"[Rr]escission of the subsequent referral denied[^.]*", None, {}),',
    '("subsequent_referral_denied", r"[Rr]escissi(on|ng) of (the )?subsequent referral[^.]*denied[^.]*", None, {}),\n    ("referral_rescinded_reref",    r"[Rr]eferral rescinded by order[^.]*", "committee", {}),\n    ("subseq_referral_resc_denied", r"[Ss]ubsequent referral rescission denied[^.]*", None, {}),')

# 3. Not-concurring parenthetical
src = src.replace(
    '("concurred",',
    '("not_concurring_paren",       r"\\(Not concurring:[^)]+\\)", None, {}),\n    ("concurred",')

# 4. Conflict of interest (bare form)
src = src.replace(
    r'[Pp]otential conflict\(?s?\)?( of interest)? declared[^.]*',
    r'[^.]*(declared|moved)[^.]*conflict of interest[^.]*')

# 5. Typo: unanimaous
src = src.replace(
    r'[^.]*(excused|absent), granted unanimous consent to vote[^.]*',
    r'[^.]*(excused|absent)[^.]*granted unanim[oa]+us consent to[^.]*')

# 6. Reconsideration (different phrasing)
src = src.replace(
    r'[^.]*served notice of possible reconsideration',
    r'[^.]*(served notice of|moved for)[^.]*reconsideration[^.]*')

# 7. Line-item veto
src = src.replace(
    '("governor_vetoed",',
    '("line_item_veto",             r"Governor purported to sign with line-item veto", "vetoed", {"veto_type": "line_item"}),\n    ("governor_vetoed",')

# 8. second_reading -> passed (rules suspended passage from second reading)
src = src.replace(
    '"second_reading": {"third_reading", "committee", "failed"},',
    '"second_reading": {"third_reading", "committee", "failed", "passed"},')

# 9. passed -> second_reading (concurrence re-read)
src = src.replace(
    '"passed": {"signed_by_presiding", "passed", "committee", "third_reading", "tabled",',
    '"passed": {"signed_by_presiding", "passed", "committee", "third_reading", "tabled", "second_reading", "failed",')

# 10. third_reading -> signed_by_presiding (rare skip)
src = src.replace(
    '"third_reading": {"passed", "adopted", "failed", "committee", "third_reading", "second_reading"},',
    '"third_reading": {"passed", "adopted", "failed", "committee", "third_reading", "second_reading", "signed_by_presiding"},')

# 11. None -> third_reading (resolutions entering second chamber at final reading)
src = src.replace(
    'None: {"introduced", "adopted"},',
    'None: {"introduced", "adopted", "third_reading"},')

open('replay_harness.py', 'w').write(src)
print('patched')
