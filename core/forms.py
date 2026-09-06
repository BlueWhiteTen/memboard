from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Group, Memory, FriendGroup, UserProfile, EDIT_PERMISSION_CHOICES
from .image_utils import compress_image

# Generous but bounded — this is a personal memory board, not a media host.
VIDEO_MAX_BYTES = 50 * 1024 * 1024   # 50MB
VOICE_MAX_BYTES = 15 * 1024 * 1024   # 15MB


def validate_media_upload(f, max_bytes, label):
    """Shared size check for the video/voice-note fields on a memory. Type
    is left to the browser's accept= filter — trusting it is fine here since
    a mis-typed file just fails to play back, nothing security-sensitive."""
    if f and not isinstance(f, str) and f.size > max_bytes:
        raise forms.ValidationError(
            f"That {label} is too large ({f.size // (1024*1024)}MB) — "
            f"the limit is {max_bytes // (1024*1024)}MB.")
    return f


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Django's FileField only accepts one upload; this is the standard
    workaround for a real multi-file <input multiple> field. clean() runs
    the normal FileField validation on every file in the list."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data if d]
        return [single_file_clean(data, initial)] if data else []


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
        fields = ('name', 'description', 'privacy', 'visible_to_group', 'cover_photo')
        widgets = {
            'name':        forms.TextInput(attrs={'placeholder': 'e.g. Summer Trip 2024, Book Club…'}),
            'description': forms.Textarea(attrs={'placeholder': 'What is this board about?', 'rows': 3}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visible_to_group'].required = False
        self.fields['visible_to_group'].queryset = (
            FriendGroup.objects.filter(owner=owner) if owner is not None else FriendGroup.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('privacy') == 'friend_group' and not cleaned.get('visible_to_group'):
            self.add_error('visible_to_group', "Choose which friend group can see this board.")
        return cleaned

    def clean_cover_photo(self):
        photo = self.cleaned_data.get('cover_photo')
        if photo and not isinstance(photo, str):
            photo = compress_image(photo)
        return photo


class GroupCoverForm(forms.ModelForm):
    class Meta:
        model  = Group
        fields = ('cover_photo',)

    def clean_cover_photo(self):
        photo = self.cleaned_data.get('cover_photo')
        if photo and not isinstance(photo, str):
            photo = compress_image(photo)
        return photo


class GroupSettingsForm(forms.ModelForm):
    class Meta:
        model  = Group
        fields = ('privacy', 'visible_to_group', 'memory_delete_permission', 'board_delete_permission')

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['visible_to_group'].required = False
        self.fields['visible_to_group'].queryset = (
            FriendGroup.objects.filter(owner=owner) if owner is not None else FriendGroup.objects.none()
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('privacy') == 'friend_group' and not cleaned.get('visible_to_group'):
            self.add_error('visible_to_group', "Choose which friend group can see this board.")
        return cleaned


class FriendGroupForm(forms.ModelForm):
    class Meta:
        model  = FriendGroup
        fields = ('name',)
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Close friends, Family, Uni mates…'}),
        }


class MemoryForm(forms.ModelForm):
    tagged = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple)
    memory_date   = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    location_name = forms.CharField(required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Add a place…', 'id': 'location-name-input'}))
    location_lat  = forms.FloatField(required=False, widget=forms.HiddenInput())
    location_lng  = forms.FloatField(required=False, widget=forms.HiddenInput())
    # Not a Memory model field — extra photos live on MemoryPhoto and are
    # saved separately in the view after this form saves the memory itself.
    extra_photos  = MultipleFileField(required=False)

    class Meta:
        model  = Memory
        fields = ('title', 'content', 'colour', 'photo', 'video', 'voice_note', 'tagged',
                  'edit_permission', 'memory_date', 'location_name', 'location_lat', 'location_lng')
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

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and not isinstance(photo, str):
            photo = compress_image(photo)
        return photo

    def clean_extra_photos(self):
        photos = self.cleaned_data.get('extra_photos') or []
        return [compress_image(p) for p in photos]

    def clean_video(self):
        return validate_media_upload(self.cleaned_data.get('video'), VIDEO_MAX_BYTES, 'video')

    def clean_voice_note(self):
        return validate_media_upload(self.cleaned_data.get('voice_note'), VOICE_MAX_BYTES, 'voice note')


class EditMemoryForm(forms.ModelForm):
    tagged = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple)
    memory_date   = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    location_name = forms.CharField(required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Add a place…', 'id': 'location-name-input'}))
    location_lat  = forms.FloatField(required=False, widget=forms.HiddenInput())
    location_lng  = forms.FloatField(required=False, widget=forms.HiddenInput())
    extra_photos  = MultipleFileField(required=False)

    class Meta:
        model  = Memory
        fields = ('title', 'content', 'colour', 'photo', 'video', 'voice_note', 'tagged',
                  'edit_permission', 'memory_date', 'location_name', 'location_lat', 'location_lng')
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

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and not isinstance(photo, str):
            photo = compress_image(photo)
        return photo

    def clean_extra_photos(self):
        photos = self.cleaned_data.get('extra_photos') or []
        return [compress_image(p) for p in photos]

    def clean_video(self):
        return validate_media_upload(self.cleaned_data.get('video'), VIDEO_MAX_BYTES, 'video')

    def clean_voice_note(self):
        return validate_media_upload(self.cleaned_data.get('voice_note'), VOICE_MAX_BYTES, 'voice note')


class FriendRequestForm(forms.Form):
    query = forms.EmailField(max_length=200,
        widget=forms.EmailInput(attrs={'placeholder': 'Their email address…'}))

    def __init__(self, *args, from_user=None, **kwargs):
        self.from_user = from_user
        super().__init__(*args, **kwargs)

    def clean_query(self):
        from .models import Friendship, FriendRequest as FR, FriendInvite
        q = self.cleaned_data['query'].strip()
        user = User.objects.filter(email__iexact=q).first()
        if user:
            if user == self.from_user:
                raise forms.ValidationError("That's you!")
            if Friendship.are_friends(self.from_user, user):
                raise forms.ValidationError(f"You're already friends with {user.get_full_name()}.")
            if FR.objects.filter(from_user=self.from_user, to_user=user).exists():
                raise forms.ValidationError(f"You already sent a request to {user.get_full_name()}.")
            self._resolved_user = user
        else:
            # No account yet — we'll email them an invite instead (handled
            # by the view). Just make sure we're not re-inviting the same
            # address needlessly.
            if FriendInvite.objects.filter(from_user=self.from_user, email__iexact=q, accepted=False).exists():
                raise forms.ValidationError("You already invited that address — waiting for them to sign up.")
            self._resolved_user = None
        return q


class ProfileForm(forms.ModelForm):
    class Meta:
        model  = UserProfile
        fields = ('bio', 'location', 'birthday', 'info_visibility')
        widgets = {
            'bio':      forms.TextInput(attrs={'placeholder': 'A short line about you…', 'maxlength': 200}),
            'location': forms.TextInput(attrs={'placeholder': 'e.g. Oxford, UK'}),
            'birthday': forms.DateInput(attrs={'type': 'date'}),
        }
