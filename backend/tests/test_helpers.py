from datetime import date

from apps.reference.constants import Gender
from apps.reference.national_id import parse_national_id
from tests.helpers import fake_national_id


def test_fake_national_id_round_trips():
    for serial in range(12):
        for gender in Gender:
            value = fake_national_id(date(1985, 6, 15), gender, serial=serial)
            info = parse_national_id(value)
            assert info.gender == gender
            assert info.date_of_birth == date(1985, 6, 15)


def test_fake_national_ids_are_unique_per_serial():
    ids = {fake_national_id(date(2015, 1, 1), Gender.MALE, serial=s) for s in range(500)}
    assert len(ids) == 500
