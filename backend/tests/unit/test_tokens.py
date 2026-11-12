from app.retrieval.tokens import extract_technical_tokens as ext


def test_error_codes_and_dotted_names_preserved():
    toks = ext("Calling BulkExportService.export() raised NIMBUS_LIMIT_EXCEEDED_0427.")
    assert "nimbus_limit_exceeded_0427" in toks
    assert "bulkexportservice.export" in toks


def test_case_styles_and_versions():
    toks = ext("Use lockRetryUtil or LockRetryUtil with snake_case_name on v2.1 and Spring '25")
    assert {"lockretryutil", "snake_case_name", "v2.1", "spring25"} <= set(toks)


def test_plain_prose_yields_nothing():
    assert ext("The quick brown fox jumps over the lazy dog") == []


def test_deduplicated_and_capped():
    text = " ".join(f"TOKEN_{i}" for i in range(500)) + " TOKEN_1"
    toks = ext(text)
    assert len(toks) == len(set(toks)) <= 200
