import factory

from apps.applications.factories import ApplicationFactory
from apps.reference.constants import Kinship

from .models import Beneficiary


class BeneficiaryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Beneficiary

    application = factory.SubFactory(ApplicationFactory)
    row_number = factory.LazyAttribute(lambda o: o.application.beneficiaries.count() + 1)
    kinship = Kinship.SON_MINOR
    full_name = "عمر أحمد محمد"
    birth_year = 2015
    national_id = None
