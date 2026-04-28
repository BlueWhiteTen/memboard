from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Group, Memory, EDIT_PERMISSION_CHOICES


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Alex'}))
    last_name = forms.CharField(max_length=50, required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Smith'}))
    email = forms.EmailField(required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))

    class Meta:
        model  = User
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username   = self.cleaned_data['email'][:150]
        user.email      = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name'].strip()
        user.last_name  = self.cleaned_data['last_name'].strip()
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'your@email.com'}))
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}))

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user    = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email    = self.cleaned_data.get('email', '').strip().lower()
        password = self.cleaned_data.get('password', '')
        if email and password:
            self.user = authenticate(self.request, username=email, password=password)
            if self.user is None:
                raise forms.ValidationError("Incorrect email or password.")
            if not self.user.is_active:
                raise forms.ValidationError("This account is inactive.")
        return self.cleaned_data

    def get_user(self):
        return self.user


class GroupForm(forms.ModelForm):
    class Meta:
        model  = Group
        fields = ('name', 'description', 'privacy', 'cover_photo')
        widgets = {
            'name':        forms.TextInput(attrs={'placeholder': 'e.g. Summer Trip 2024, Book Club…'}),
            'description': forms.Textarea(attrs={'placeholder': 'What is this board about?', 'rows': 3}),
        }


class GroupCoverForm(forms.ModelForm):
    class Meta:
        model  = Group
        fields = ('cover_photo',)


class MemoryForm(forms.ModelForm):
    tagged = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple)
    memory_date   = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    location_name = forms.CharField(required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Add a place…', 'id': 'location-name-input'}))
    location_lat  = forms.FloatField(required=False, widget=forms.HiddenInput())
    location_lng  = forms.FloatField(required=False, widget=forms.HiddenInput())

    class Meta:
        model  = Memory
        fields = ('title', 'content', 'colour', 'photo', 'tagged', 'edit_permission',
                  'memory_date', 'location_name', 'location_lat', 'location_lng')
        widgets = {
            'title':           forms.TextInput(attrs={'placeholder': 'Give this memory a name… (optional)'}),
            'content':         forms.Textarea(attrs={'placeholder': 'Write your memory here…', 'rows': 5}),
            'colour':          forms.HiddenInput(),
            'edit_permission': forms.HiddenInput(),
        }

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group:
            self.fields['tagged'].queryset = group.members.all()


class EditMemoryForm(forms.ModelForm):
    tagged = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple)
    memory_date   = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    location_name = forms.CharField(required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Add a place…', 'id': 'location-name-input'}))
    location_lat  = forms.FloatField(required=False, widget=forms.HiddenInput())
    location_lng  = forms.FloatField(required=False, widget=forms.HiddenInput())

    class Meta:
        model  = Memory
        fields = ('title', 'content', 'colour', 'photo', 'tagged', 'edit_permission',
                  'memory_date', 'location_name', 'location_lat', 'location_lng')
        widgets = {
            'title':           forms.TextInput(attrs={'placeholder': 'Give this memory a name… (optional)'}),
            'content':         forms.Textarea(attrs={'placeholder': 'Write your memory here…', 'rows': 5}),
            'colour':          forms.HiddenInput(),
            'edit_permission': forms.HiddenInput(),
        }

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group:
            self.fields['tagged'].queryset = group.members.all()


class InviteMemberForm(forms.Form):
    username = forms.CharField(max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Enter a username…'}))

    def __init__(self, *args, group=None, **kwargs):
        self.group = group
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError("No user with that username exists.")
        if self.group and self.group.members.filter(pk=user.pk).exists():
            raise forms.ValidationError(f"{user.get_full_name()} is already a member.")
        self._resolved_user = user
        return username


class FriendRequestForm(forms.Form):
    query = forms.CharField(max_length=200,
        widget=forms.TextInput(attrs={'placeholder': 'Name or email address…'}))

    def __init__(self, *args, from_user=None, **kwargs):
        self.from_user = from_user
        super().__init__(*args, **kwargs)

    def clean_query(self):
        from .models import Friendship, FriendRequest as FR
        q = self.cleaned_data['query'].strip()
        user = None
        if '@' in q:
            user = User.objects.filter(email__iexact=q).first()
        if not user:
            parts = q.split()
            if len(parts) >= 2:
                user = User.objects.filter(
                    first_name__iexact=parts[0],
                    last_name__iexact=' '.join(parts[1:])
                ).first()
        if not user:
            qs = User.objects.filter(first_name__iexact=q)
            if qs.count() == 1:
                user = qs.first()
        if not user:
            raise forms.ValidationError("No Memboard account found. Try their email address.")
        if user == self.from_user:
            raise forms.ValidationError("That's you!")
        if Friendship.are_friends(self.from_user, user):
            raise forms.ValidationError(f"You're already friends with {user.get_full_name()}.")
        if FR.objects.filter(from_user=self.from_user, to_user=user).exists():
            raise forms.ValidationError(f"You already sent a request to {user.get_full_name()}.")
        self._resolved_user = user
        return q
