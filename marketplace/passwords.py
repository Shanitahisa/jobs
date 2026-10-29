import re
from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    def validate(self,password,user=None):
        errors=[]
        if len(password)>128:errors.append('Use no more than 128 characters.')
        if not re.search(r'[A-Z]',password):errors.append('Include an uppercase letter.')
        if not re.search(r'[a-z]',password):errors.append('Include a lowercase letter.')
        if not re.search(r'[0-9]',password):errors.append('Include a number.')
        if not re.search(r'[^\w\s]',password):errors.append('Include a special character.')
        if re.search(r'\s',password):errors.append('Do not include spaces or other whitespace.')
        if errors:raise ValidationError(errors)
    def get_help_text(self):
        return 'Use 8–128 characters, including uppercase, lowercase, a number and a special character, without whitespace.'
