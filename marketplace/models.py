from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=12, choices=[('worker','Worker'),('employer','Employer')])
    name = models.CharField(max_length=120)
    headline = models.CharField(max_length=180, blank=True)
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    situation = models.CharField(max_length=30, default='unemployed', choices=[('unemployed','Unemployed'),('employed','Employed'),('student','Student'),('self_employed','Self-employed')])
    availability = models.CharField(max_length=30, default='immediately', choices=[('immediately','Immediately'),('weekdays','Weekdays'),('weekends','Weekends'),('evenings','Evenings')])
    work_types = models.JSONField(default=list)
    professions = models.JSONField(default=list)
    experience = models.PositiveIntegerField(default=0)
    rate = models.DecimalField(max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    portfolio = models.URLField(blank=True)
    projects = models.JSONField(default=list)
    work_history = models.JSONField(default=list)
    published = models.BooleanField(default=False)
    page_slug = models.SlugField(max_length=80,unique=True,null=True,blank=True)
    photo = models.FileField(upload_to='profile-photos/%Y/%m/',blank=True)

    def save(self,*args,**kwargs):
        if self.published and self.role=='worker' and not self.page_slug:
            from django.utils.text import slugify
            import uuid
            base=(slugify(self.name)[:50] or 'talent')+'-'+str(self.user_id)
            candidate=base
            while Profile.objects.filter(page_slug=candidate).exclude(pk=self.pk).exists():candidate=base+'-'+uuid.uuid4().hex[:6]
            self.page_slug=candidate
            if kwargs.get('update_fields') is not None:kwargs['update_fields']=set(kwargs['update_fields'])|{'page_slug'}
        super().save(*args,**kwargs)


class Business(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='business')
    name = models.CharField(max_length=150)
    industry = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    registration_number = models.CharField(max_length=100)
    website = models.URLField(blank=True)
    status = models.CharField(max_length=20, default='draft', choices=[('draft','Draft'),('pending','Under review'),('approved','Approved'),('changes','Changes requested'),('rejected','Rejected')])
    review_note = models.TextField(blank=True)


class Document(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, choices=[('cv','CV'),('certificate','Certification'),('clearance','Professional clearance'),('registration','Registration certificate'),('licence','Trading licence')])
    profession = models.CharField(max_length=120, blank=True)
    skill = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=150)
    file = models.FileField(upload_to='private/%Y/%m/')
    status = models.CharField(max_length=20, default='pending', choices=[('pending','Pending'),('verified','Verified'),('rejected','Rejected')])
    review_note = models.TextField(blank=True)
    expires = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProjectImage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to='projects/%Y/%m/')
    created_at = models.DateTimeField(auto_now_add=True)


class Opportunity(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='opportunities')
    title = models.CharField(max_length=150)
    description = models.TextField()
    profession = models.CharField(max_length=100)
    skills = models.JSONField(default=list)
    preferred_skills = models.JSONField(default=list)
    location = models.CharField(max_length=100)
    remote = models.BooleanField(default=False)
    work_type = models.CharField(max_length=20, choices=[('gig','Gig'),('full_time','Full-time'),('part_time','Part-time'),('internship','Internship')], default='gig')
    availability = models.CharField(max_length=30, default='flexible', choices=[('flexible','Flexible'),('immediately','Immediately'),('weekdays','Weekdays'),('weekends','Weekends'),('evenings','Evenings')])
    start_date = models.DateField()
    end_date = models.DateField()
    budget = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(1)])
    deliverables = models.TextField()
    minimum_experience = models.PositiveIntegerField(default=0)
    required_certificate = models.BooleanField(default=False)
    required_clearance = models.BooleanField(default=False)
    status = models.CharField(max_length=15, default='open', choices=[('open','Open'),('closed','Closed')])
    created_at = models.DateTimeField(auto_now_add=True)


class Interest(models.Model):
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='interests')
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['worker','opportunity'], name='unique_interest')]


class Shortlist(models.Model):
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name='shortlists')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['worker','opportunity'], name='unique_shortlist')]


class Engagement(models.Model):
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='engagements')
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='offered', choices=[(x,x.replace('_',' ').title()) for x in ['offered','accepted','hired','funded','submitted','approved','completed','disputed','cancelled']])
    work_type = models.CharField(max_length=20, default='gig')
    agreed_amount = models.DecimalField(max_digits=12, decimal_places=0)
    agreed_deliverables = models.TextField()
    agreed_start = models.DateField()
    agreed_end = models.DateField()
    submission = models.TextField(blank=True)
    note = models.TextField(blank=True)
    payment_mode = models.CharField(max_length=20, default='demo')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['worker','opportunity'], name='unique_engagement')]


class WorkSubmission(models.Model):
    engagement = models.ForeignKey(Engagement,on_delete=models.CASCADE,related_name='submissions')
    notes = models.TextField()
    links = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-id']


class SubmissionAttachment(models.Model):
    engagement = models.ForeignKey(Engagement,on_delete=models.CASCADE,related_name='attachments')
    submission = models.ForeignKey(WorkSubmission,on_delete=models.CASCADE,related_name='attachments',null=True,blank=True)
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    file = models.FileField(upload_to='private/submissions/%Y/%m/')
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=10,choices=[('image','Image'),('document','Document')])
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class AdminAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    action = models.CharField(max_length=80)
    record_type = models.CharField(max_length=60)
    record_id = models.PositiveIntegerField()
    note = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-id']


class Payment(models.Model):
    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name='payments')
    reference = models.CharField(max_length=100, unique=True)
    provider_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    status = models.CharField(max_length=20, default='pending')
    mode = models.CharField(max_length=20, default='demo')
    created_at = models.DateTimeField(auto_now_add=True)


class PayoutAccount(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    beneficiary_name = models.CharField(max_length=120)
    network = models.CharField(max_length=12, choices=[('MTN','MTN'),('Airtel','Airtel')])
    number = models.CharField(max_length=12)


class Review(models.Model):
    engagement = models.ForeignKey(Engagement, on_delete=models.CASCADE, related_name='reviews')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['engagement','author'], name='unique_review')]


class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    email_enabled = models.BooleanField(default=True)
    opportunity_alerts = models.BooleanField(default=True)
    activity_alerts = models.BooleanField(default=True)
    payment_alerts = models.BooleanField(default=True)
    browser_alerts = models.BooleanField(default=False)


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='notifications')
    category = models.CharField(max_length=20)
    title = models.CharField(max_length=180)
    message = models.TextField()
    target = models.JSONField(default=dict)
    event_key = models.CharField(max_length=200,unique=True)
    read_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at','-id']
        indexes=[models.Index(fields=['user','read_at','created_at'])]


class EmailDelivery(models.Model):
    notification = models.OneToOneField(Notification,on_delete=models.CASCADE,related_name='email_delivery')
    status = models.CharField(max_length=20,default='queued',choices=[(x,x.replace('_',' ').title()) for x in ['queued','sending','accepted','retry','failed','uncertain','suppressed']])
    attempts = models.PositiveSmallIntegerField(default=0)
    provider_id = models.CharField(max_length=200,blank=True)
    last_error = models.CharField(max_length=250,blank=True)
    next_attempt = models.DateTimeField(default=timezone.now)
    claimed_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['created_at']
