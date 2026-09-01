from datetime import UTC, datetime

from swe_job_radar.classification import RuleBasedClassifier
from swe_job_radar.classification.graduation import graduation_window_matches
from swe_job_radar.models import Classification, Job, Priority


def job(title: str, description: str = "", location: str | None = "New York, NY") -> Job:
    return Job(
        company="Example",
        external_id="1",
        title=title,
        location=location,
        description=description,
        job_url="https://example.com/jobs/1",
        apply_url=None,
        employment_type=None,
        date_posted=None,
        first_seen_at=datetime.now(UTC),
        source_url="https://example.com/careers",
    )


def classify(value: Job, priority: Priority = Priority.CRITICAL) -> Classification:
    return RuleBasedClassifier().classify(value, priority).classification


def test_2027_internship_and_graduation_window() -> None:
    value = job(
        "Backend Engineer Intern — Summer 2027",
        "Expected graduation between December 2027 and June 2028.",
    )
    assert classify(value) is Classification.INTERN_2027


def test_new_grad_from_zero_to_one_year_requirement() -> None:
    value = job("Software Engineer I", "Requires 0-1 years experience. Start in 2027.")
    assert classify(value) is Classification.NEW_GRAD_2027


def test_generic_swe_is_ambiguous() -> None:
    assert classify(job("Software Engineer")) is Classification.RELEVANT_BUT_AMBIGUOUS


def test_internship_graduation_year_is_not_mistaken_for_season() -> None:
    value = job("SDE Intern", "Candidates should graduate in May 2028.")
    assert classify(value) is Classification.RELEVANT_BUT_AMBIGUOUS


def test_senior_and_experience_filters() -> None:
    assert classify(job("Senior Software Engineer")) is Classification.IRRELEVANT
    assert classify(job("Backend Engineer", "Requires 5+ years professional experience")) is (
        Classification.IRRELEVANT
    )


def test_quant_filtering() -> None:
    assert (
        classify(job("Quantitative Researcher Intern"), Priority.QUANT) is Classification.IRRELEVANT
    )
    assert classify(job("Quantitative Software Engineer", "2027 new graduate"), Priority.QUANT) is (
        Classification.NEW_GRAD_2027
    )


def test_non_us_and_unknown_location() -> None:
    assert classify(job("Software Engineer Intern 2027", location="London, UK")) is (
        Classification.IRRELEVANT
    )
    assert classify(job("Software Engineer Intern", location=None)) is (
        Classification.RELEVANT_BUT_AMBIGUOUS
    )


def test_graduation_window_parser() -> None:
    from datetime import date

    assert (
        graduation_window_matches(
            "Expected graduation between December 2027 and June 2028", date(2028, 5, 1)
        )
        is True
    )
    assert (
        graduation_window_matches(
            "Expected graduation between December 2026 and August 2027", date(2028, 5, 1)
        )
        is False
    )
