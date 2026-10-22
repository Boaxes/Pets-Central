from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from catalog.models import Product
from customers.models import Customer
from inventory.models import Animal, StockLevel
from stores.models import Employee

DATE = forms.DateInput(attrs={'type': 'date'})


class StoreFormMixin:
    """Forms know the request, so choices and saves stay inside the signed-in user's store."""

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)

    @property
    def store(self):
        return self.request.store


class EmailCheck:
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError('Please enter a valid email address.')
        return email


class CustomerCreateForm(StoreFormMixin, EmailCheck, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name', 'email', 'phone', 'postal_code', 'marketing_opt_in']
        labels = {'phone': 'Phone number', 'marketing_opt_in': 'Agreed to marketing emails'}

    def save(self, commit=True):
        self.instance.home_store = self.store
        return super().save(commit)


class CustomerUpdateForm(StoreFormMixin, EmailCheck, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['email', 'phone', 'postal_code', 'marketing_opt_in']
        labels = {'phone': 'Phone number', 'marketing_opt_in': 'Agreed to marketing emails'}


HIREABLE_ROLES = [(value, label) for value, label in Employee.Role.choices if value != Employee.Role.STORE_MANAGER]


class EmployeeHireForm(StoreFormMixin, EmailCheck, forms.ModelForm):
    role = forms.ChoiceField(choices=HIREABLE_ROLES, help_text='Store managers are appointed by corporate.')

    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'role', 'hourly_rate', 'hired_on']
        widgets = {'hired_on': DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hired_on'].initial = date.today()


class EmployeeUpdateForm(StoreFormMixin, EmailCheck, forms.ModelForm):
    role = forms.ChoiceField(choices=HIREABLE_ROLES)

    class Meta:
        model = Employee
        fields = ['role', 'hourly_rate', 'email']


class TerminateForm(StoreFormMixin, forms.Form):
    terminated_on = forms.DateField(widget=DATE, initial=date.today, label='Last day')


class AnimalReceiveForm(StoreFormMixin, forms.ModelForm):
    class Meta:
        model = Animal
        fields = ['product', 'name', 'sex', 'born_on', 'received_on']
        labels = {'product': 'Species', 'born_on': 'Born on (if known)'}
        widgets = {'born_on': DATE, 'received_on': DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = (Product.objects.filter(species__isnull=False)
                                           .select_related('species').order_by('species__common_name'))
        self.fields['product'].label_from_instance = lambda p: p.species.common_name
        self.fields['received_on'].initial = date.today()

    def clean(self):
        cleaned = super().clean()
        born, received = cleaned.get('born_on'), cleaned.get('received_on')
        if born and received and born > received:
            raise ValidationError('An animal must be born before it arrives.')
        return cleaned

    def save(self, commit=True):
        self.instance.store = self.store
        return super().save(commit)


class AnimalUpdateForm(StoreFormMixin, forms.ModelForm):
    class Meta:
        model = Animal
        fields = ['name', 'sex', 'born_on']
        widgets = {'born_on': DATE}


class RemoveAnimalForm(StoreFormMixin, forms.Form):
    removed_on = forms.DateField(widget=DATE, initial=date.today)
    removal_reason = forms.ChoiceField(choices=Animal.RemovalReason.choices, label='Reason')


class AssignCaretakerForm(StoreFormMixin, forms.Form):
    animal = forms.ModelChoiceField(queryset=Animal.objects.none())
    employee = forms.ModelChoiceField(queryset=Employee.objects.none(), label='Caretaker')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['animal'].queryset = (Animal.objects.available().filter(store=self.store)
                                          .select_related('product__species', 'store').order_by('received_on'))
        self.fields['employee'].queryset = Employee.objects.filter(
            store=self.store, terminated_on__isnull=True,
            role__in=[Employee.Role.ANIMAL_CARE, Employee.Role.STORE_MANAGER, Employee.Role.ASSISTANT_MANAGER],
        ).order_by('last_name')
        self.fields['employee'].label_from_instance = lambda e: f'{e} ({e.get_role_display()})'


class StockForm(StoreFormMixin, forms.ModelForm):
    class Meta:
        model = StockLevel
        fields = ['quantity_on_hand', 'reorder_point']
        labels = {'quantity_on_hand': 'Quantity on hand (after a count)'}
