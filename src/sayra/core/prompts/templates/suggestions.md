Generate exactly $suggestion_count possible learner replies in $target_language at CEFR
$difficulty_level with the additional exam constraint $exam_level. Translate every reply
into $native_language.

Return JSON only in this exact shape:
{"suggestions":[{"target_text":"target-language reply","native_text":"translation"}]}
