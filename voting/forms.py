# voting/forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
import re
from .models import (
    User, School, Department, Party, Candidate, Election, Vote, Feedback, ContactMessage
)

# ------------------------------------------------------------------
# Helper validators
# ------------------------------------------------------------------
def validate_kenyan_phone(phone):
    """Raise ValidationError if phone number is not a valid Kenyan number."""
    if not re.match(r'^(?:\+254|0|1)[0-9]{9}$', phone):
        raise ValidationError("Phone number must be a valid Kenyan number: +254XXXXXXXXX, 07XXXXXXXX, or 01XXXXXXXX.")

# voting/forms.py (excerpt – replace UserRegistrationForm, CandidateRegistrationForm, UserProfileForm)

# ------------------------------------------------------------------
# User Registration Form
# ------------------------------------------------------------------
class UserRegistrationForm(UserCreationForm):
    """Multi-role registration form with dynamic fields based on role."""
    role = forms.ChoiceField(choices=User.ROLES, widget=forms.RadioSelect)
    phone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'placeholder': 'e.g., +254712345678'}))
    security_question = forms.ChoiceField(choices=User.SECURITY_QUESTIONS)
    security_answer = forms.CharField(max_length=255, widget=forms.TextInput(attrs={'placeholder': 'Your answer'}))
    id_type = forms.ChoiceField(choices=User.ID_TYPES, widget=forms.RadioSelect)
    id_photo = forms.ImageField(required=True, help_text="Upload a clear photo of your ID card.")
    
    # Student-specific fields
    admission_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g., SCI/001/21'}))
    course = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g., Computer Science'}))
    year_of_study = forms.IntegerField(required=False, min_value=1, max_value=6, widget=forms.NumberInput(attrs={'placeholder': 'e.g., 3'}))
    school = forms.ModelChoiceField(queryset=School.objects.all(), required=False, empty_label="Select School")
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False, empty_label="Select Department")
    residence = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g., Main Campus, Town Campus'}))
    polling_station = forms.CharField(
        max_length=100, required=False,
        label="Polling Venue",
        help_text="Physical voting venue (auto-filled based on residence)"
    )
    
    # Staff-specific fields
    staff_id = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'placeholder': 'MMUST Staff ID'}))
    department_work = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g., School of Computing'}))

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email', 'password1', 'password2',
            'role', 'phone', 'security_question', 'security_answer', 'id_type', 'id_photo',
            'admission_number', 'course', 'year_of_study', 'school', 'department',
            'residence', 'polling_station', 'staff_id', 'department_work'
        )
        widgets = {
            'username': forms.TextInput(attrs={'placeholder': 'e.g., johndoe', 'autocomplete': 'username'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@mmust.ac.ke', 'autocomplete': 'email'}),
            'password1': forms.PasswordInput(attrs={'placeholder': 'Enter password', 'autocomplete': 'new-password'}),
            'password2': forms.PasswordInput(attrs={'placeholder': 'Confirm password', 'autocomplete': 'new-password'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamic department queryset based on selected school
        if 'school' in self.data:
            try:
                school_id = int(self.data.get('school'))
                self.fields['department'].queryset = Department.objects.filter(school_id=school_id).order_by('name')
            except (ValueError, TypeError):
                self.fields['department'].queryset = Department.objects.none()
        elif self.instance.pk and self.instance.school:
            self.fields['department'].queryset = Department.objects.filter(school=self.instance.school).order_by('name')
        else:
            self.fields['department'].queryset = Department.objects.none()

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            validate_kenyan_phone(phone)
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Allow @mmust.ac.ke and any subdomain like @student.mmust.ac.ke, @staff.mmust.ac.ke
            if not (email.lower().endswith('@mmust.ac.ke') or email.lower().endswith('.mmust.ac.ke')):
                raise ValidationError("Please use your official MMUST email address (e.g., @mmust.ac.ke or @student.mmust.ac.ke).")
        return email

    def clean_admission_number(self):
        admission = self.cleaned_data.get('admission_number')
        role = self.cleaned_data.get('role')
        if role in ['voter', 'candidate'] and not admission:
            raise ValidationError("Admission number is required for voters/candidates.")
        if admission and User.objects.filter(admission_number=admission).exists():
            raise ValidationError("This admission number is already registered.")
        return admission

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        # Role-based required fields
        if role in ['voter', 'candidate']:
            required_fields = ['admission_number', 'course', 'year_of_study', 'school', 'department']
            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, f'This field is required for {role}s.')
        elif role == 'polling_officer':
            if not cleaned_data.get('staff_id'):
                self.add_error('staff_id', 'Staff ID is required for polling officers.')
            if not cleaned_data.get('department_work'):
                self.add_error('department_work', 'Department is required for polling officers.')

        # Auto-set polling station based on residence (now labelled Polling Venue)
        residence = cleaned_data.get('residence')
        if residence:
            if 'main' in residence.lower():
                cleaned_data['polling_station'] = 'Main Campus - Central Hall'
            elif 'town' in residence.lower():
                cleaned_data['polling_station'] = 'Town Campus - Lecture Hall A'
            else:
                cleaned_data['polling_station'] = 'Main Campus - General Hall'
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.security_answer = self.cleaned_data['security_answer'].lower()
        if commit:
            user.save()
        return user


# ------------------------------------------------------------------
# Candidate Registration Form (UPDATED with hall, gender, school fields)
# ------------------------------------------------------------------
class CandidateRegistrationForm(forms.ModelForm):
    gender = forms.ChoiceField(choices=[('male','Male'),('female','Female')], required=True)
    hall = forms.ChoiceField(choices=[], required=False)
    school = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = Candidate
        fields = ['position', 'party', 'manifesto']

    def __init__(self, *args, **kwargs):
        self.election = kwargs.pop('election', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['manifesto'].help_text = "Write a short manifesto (max 1000 characters)."
        self.fields['party'].queryset = Party.objects.all().order_by('name')
        self.fields['party'].empty_label = "Independent (No Party)"

        # Hall choices (will be overwritten by JS but kept for validation)
        self.fields['hall'].choices = [
            ('hall1_male', 'Hall 1 (Male)'),
            ('hall2_male', 'Hall 2 (Male)'),
            ('hall3_female', 'Hall 3 (Female)'),
            ('hall4_female', 'Hall 4 (Female)'),
            ('hall4_male', 'Hall 4 (Male)'),
        ]
        self.fields['school'].choices = [
            ('sci', 'School of Computing and Informatics'),
            ('sedu', 'School of Education'),
            ('eng', 'School of Engineering'),
            ('med', 'School of Medicine'),
            ('bus', 'School of Business'),
            ('nursing', 'School of Nursing'),
        ]

    def clean(self):
        cleaned_data = super().clean()
        gender = cleaned_data.get('gender')
        position = cleaned_data.get('position')
        if not position:
            return cleaned_data
        pos_name = position.name if hasattr(position, 'name') else str(position)

        metadata = {'gender': gender}

        if pos_name == 'President (Party Ticket)':
            if not cleaned_data.get('party'):
                self.add_error('party', 'Party is required for presidential candidate.')
            metadata['is_party_presidential_candidate'] = True
        elif 'Hall' in pos_name:
            hall = cleaned_data.get('hall')
            if not hall:
                self.add_error('hall', 'Hall selection is required for Hall Representative.')
            # Validate hall matches gender
            hall_gender = 'male' if 'male' in hall else 'female'
            if hall_gender != gender:
                self.add_error('hall', f'Selected hall does not match your gender ({gender}).')
            metadata['hall'] = hall
        elif 'School Representative' in pos_name:
            school = cleaned_data.get('school')
            if not school:
                self.add_error('school', 'School selection is required.')
            metadata['school'] = school
        elif 'Non-resident' in pos_name:
            # no extra field
            pass
        else:
            # any other position – no extra fields
            pass

        cleaned_data['candidate_metadata'] = metadata
        return cleaned_data


# ------------------------------------------------------------------
# User Profile Form
# ------------------------------------------------------------------
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email', 'phone', 'security_question', 'security_answer', 'residence', 'polling_station']
        widgets = {
            'security_question': forms.Select(choices=User.SECURITY_QUESTIONS, attrs={'class': 'form-select'}),
            'security_answer': forms.PasswordInput(render_value=True, attrs={'placeholder': 'Leave blank to keep current'}),
            'email': forms.EmailInput(attrs={'placeholder': 'you@mmust.ac.ke', 'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'placeholder': 'e.g., +254712345678'}),
            'residence': forms.TextInput(attrs={'placeholder': 'e.g., Main Campus'}),
            'polling_station': forms.TextInput(attrs={'placeholder': 'Auto-filled based on residence'}),
        }
        labels = {
            'polling_station': 'Polling Venue',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['security_answer'].required = False
        self.fields['security_answer'].help_text = "Leave blank to keep current answer."

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            validate_kenyan_phone(phone)
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Allow @mmust.ac.ke and any subdomain like @student.mmust.ac.ke, @staff.mmust.ac.ke
            if not (email.lower().endswith('@mmust.ac.ke') or email.lower().endswith('.mmust.ac.ke')):
                raise ValidationError("Please use your official MMUST email address (e.g., @mmust.ac.ke or @student.mmust.ac.ke).")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('security_answer'):
            user.security_answer = self.cleaned_data['security_answer'].lower()
        if commit:
            user.save()
        return user

# ------------------------------------------------------------------
# Candidate Withdrawal Form
# ------------------------------------------------------------------
class CandidateWithdrawalForm(forms.Form):
    confirm = forms.BooleanField(label="I confirm that I want to withdraw from the election", required=True)

# ------------------------------------------------------------------
# Polling Officer Test Form (with dynamic questions)
# ------------------------------------------------------------------
class PollingOfficerTestForm(forms.Form):
    QUESTIONS = [
        {
            'id': 'q1',
            'text': 'What is the first step if a voter claims they already voted?',
            'answer_keywords': ['verify', 'voter status', 'check system', 'already cast']
        },
        {
            'id': 'q2',
            'text': 'How do you assist a voter with a disability?',
            'answer_keywords': ['assist', 'disability', 'accessible', 'reading aloud', 'trusted person']
        },
        {
            'id': 'q3',
            'text': 'What is the procedure for handling a damaged ballot?',
            'answer_keywords': ['spoil', 'issue new', 'record', 'incident']
        },
        {
            'id': 'q4',
            'text': 'What should you do if a voter attempts to take a photo of their ballot?',
            'answer_keywords': ['prohibit', 'explain rules', 'confiscate phone', 'report']
        },
        {
            'id': 'q5',
            'text': 'Explain the importance of voter secrecy.',
            'answer_keywords': ['privacy', 'free choice', 'no coercion', 'anonymous']
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for q in self.QUESTIONS:
            self.fields[q['id']] = forms.CharField(
                label=q['text'],
                widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Your answer...'}),
                required=True
            )

    def grade(self):
        """Grade the test based on keyword matching. Returns (score_percent, answers_dict)."""
        cleaned_data = self.cleaned_data
        total = len(self.QUESTIONS)
        score = 0
        answers = {}
        for q in self.QUESTIONS:
            qid = q['id']
            answer = cleaned_data.get(qid, '').lower().strip()
            answers[qid] = answer
            keywords = q['answer_keywords']
            match_count = sum(1 for kw in keywords if kw in answer)
            if match_count >= len(keywords) // 2:   # At least half keywords present
                score += 1
        percentage = int((score / total) * 100)
        return percentage, answers

    def get_passing_score(self):
        return 80   # override if needed

# ------------------------------------------------------------------
# Login Form (with security question challenge)
# ------------------------------------------------------------------
class VotingLoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    security_answer = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput,
                                      help_text="Answer your security question (required on voting day)")

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        security_answer = cleaned_data.get('security_answer')
        from django.contrib.auth import authenticate
        user = authenticate(username=username, password=password)
        if not user:
            raise ValidationError("Invalid username or password.")
        # Check if voting is ongoing and require security answer
        now = timezone.now()
        election = Election.objects.filter(start_time__lte=now, end_time__gte=now).first()
        if election and not security_answer:
            raise ValidationError("Security answer is required during voting period.")
        if security_answer and user.security_answer.lower() != security_answer.lower():
            raise ValidationError("Incorrect security answer.")
        cleaned_data['user'] = user
        return cleaned_data

# ------------------------------------------------------------------
# Vote Encryption Form (dynamic ballot)
# ------------------------------------------------------------------
class VoteForm(forms.Form):
    """Dynamic form for ballot submission."""
    def __init__(self, positions_candidates, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for position, candidates in positions_candidates.items():
            choices = [(c.id, f"{c.user.get_full_name()} ({c.party.abbreviation if c.party else 'Indep.'})") for c in candidates]
            self.fields[f'position_{position.id}'] = forms.ChoiceField(
                label=position.name,
                choices=choices,
                widget=forms.RadioSelect,
                required=False,
            )

# ------------------------------------------------------------------
# Broadcast Notification Form
# ------------------------------------------------------------------
class BroadcastNotificationForm(forms.Form):
    subject = forms.CharField(max_length=255)
    message = forms.CharField(widget=forms.Textarea)
    send_to = forms.ChoiceField(choices=[
        ('all', 'All Users'),
        ('voters', 'Voters Only'),
        ('candidates', 'Candidates Only'),
        ('polling_officers', 'Polling Officers Only'),
        ('admins', 'Admins Only'),
    ])
    via_email = forms.BooleanField(required=False, initial=True)
    via_sms = forms.BooleanField(required=False)

# ------------------------------------------------------------------
# Receipt Verification Form
# ------------------------------------------------------------------
class ReceiptVerificationForm(forms.Form):
    receipt_id = forms.CharField(max_length=64, label="Vote Receipt ID",
                                 help_text="Enter the receipt you received after voting.")

    def clean_receipt_id(self):
        receipt_id = self.cleaned_data.get('receipt_id')
        if not Vote.objects.filter(receipt_id=receipt_id).exists():
            raise ValidationError("No vote found with this receipt ID.")
        return receipt_id

# ------------------------------------------------------------------
# Admin Candidate Verification Form (UPDATED with has_cleared_fees)
# ------------------------------------------------------------------
class CandidateVerificationForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = ['verified', 'missing_marks', 'supplementary_exams', 'has_cleared_fees']
        widgets = {
            'verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'missing_marks': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'supplementary_exams': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_cleared_fees': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        verified = cleaned_data.get('verified')
        missing_marks = cleaned_data.get('missing_marks')
        supp = cleaned_data.get('supplementary_exams')
        if verified and (missing_marks or supp):
            raise ValidationError("Cannot verify a candidate with missing marks or supplementary exams.")
        return cleaned_data

# ------------------------------------------------------------------
# Feedback Form
# ------------------------------------------------------------------
class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.RadioSelect(choices=[(1,'1'),(2,'2'),(3,'3'),(4,'4'),(5,'5')]),
            'comment': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Your feedback helps us improve...'}),
        }

    def clean_rating(self):
        rating = self.cleaned_data.get('rating')
        if rating not in [1,2,3,4,5]:
            raise ValidationError("Rating must be between 1 and 5.")
        return rating

class ContactForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'Your full name', 'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'placeholder': 'Your email address', 'class': 'form-control'}))
    subject = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'placeholder': 'Subject', 'class': 'form-control'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Your message...', 'class': 'form-control'}))

class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'What is this about?'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Write your message here...'}),
        }