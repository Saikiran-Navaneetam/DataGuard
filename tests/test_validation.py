import pytest

from application.validation.validator import validate_employee


@pytest.fixture
def valid_employee():
    return {
        "employee_id": "EMP100",
        "employee_name": "Test Employee",
        "department_id": "101",
        "salary": "50000",
        "age": "25",
        "joining_date": "2025-01-15"
    }


def test_valid_employee_has_no_errors(valid_employee):
    errors = validate_employee(valid_employee, set(), set())

    assert errors == []


def test_missing_employee_id_is_rejected(valid_employee):
    valid_employee["employee_id"] = ""

    errors = validate_employee(valid_employee, set(), set())

    assert "MISSING_EMPLOYEE_ID" in [error[0] for error in errors]


def test_invalid_department_is_rejected(valid_employee):
    valid_employee["department_id"] = "999"

    errors = validate_employee(valid_employee, set(), set())

    assert "INVALID_DEPARTMENT" in [error[0] for error in errors]


@pytest.mark.parametrize("salary", ["-5000", "0", "abc"])
def test_invalid_salary_is_rejected(valid_employee, salary):
    valid_employee["salary"] = salary

    errors = validate_employee(valid_employee, set(), set())

    assert "INVALID_SALARY" in [error[0] for error in errors]


@pytest.mark.parametrize("age", ["15", "70", "abc"])
def test_invalid_age_is_rejected(valid_employee, age):
    valid_employee["age"] = age

    errors = validate_employee(valid_employee, set(), set())

    assert "INVALID_AGE" in [error[0] for error in errors]


def test_invalid_joining_date_is_rejected(valid_employee):
    valid_employee["joining_date"] = "15-01-2025"

    errors = validate_employee(valid_employee, set(), set())

    assert "INVALID_JOINING_DATE" in [error[0] for error in errors]


def test_duplicate_employee_id_is_rejected(valid_employee):
    errors = validate_employee(
        valid_employee,
        {"EMP100"},
        set()
    )

    assert "DUPLICATE_EMPLOYEE_ID" in [error[0] for error in errors]


def test_existing_employee_id_is_rejected(valid_employee):
    errors = validate_employee(
        valid_employee,
        set(),
        {"EMP100"}
    )

    assert "DUPLICATE_EMPLOYEE_ID" in [error[0] for error in errors]