from datetime import date

import factory

from apps.accounts.factories import UserFactory
from apps.reference.constants import Gender, Religion, SyndicateType
from tests.helpers import fake_national_id

from .models import Doctor


class DoctorFactory(factory.django.DjangoModelFactory):
    """A doctor with a complete, valid profile (born 1985, registered 2014 by default)."""

    class Meta:
        model = Doctor

    class Params:
        born = date(1985, 6, 15)

    user = factory.SubFactory(UserFactory)
    full_name = "أحمد محمد علي حسن"
    gender = Gender.MALE
    date_of_birth = factory.SelfAttribute("born")
    birth_year = factory.LazyAttribute(lambda o: o.born.year)
    national_id = factory.LazyAttributeSequence(
        lambda o, n: fake_national_id(o.born, o.gender, serial=n)
    )
    religion = Religion.MUSLIM
    phone_number = "01012345678"
    syndicate_type = SyndicateType.HUMAN_MEDICINE
    sub_syndicate = "القاهرة"
    syndicate_registration_number = factory.Sequence(lambda n: f"{10000 + n}")
    syndicate_registration_year = 2014
    governorate = "القاهرة"
    neighborhood = "مدينة نصر"
    address = "شارع عباس العقاد"
