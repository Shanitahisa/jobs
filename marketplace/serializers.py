from rest_framework import serializers
from .models import Profile, Business, Document, Opportunity, Engagement, Review, Payment, ProjectImage,Notification,NotificationPreference,SubmissionAttachment,WorkSubmission


def string_list(value, field, maximum=30):
    if not isinstance(value,list) or len(value)>maximum or any(not isinstance(s,str) or not s.strip() or len(s)>120 for s in value):
        raise serializers.ValidationError({field:'Use a list of non-empty text values (maximum 30).'})
    return list(dict.fromkeys(s.strip() for s in value))


class ProfileSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    photo_url=serializers.SerializerMethodField()
    page_url=serializers.SerializerMethodField()
    class Meta:
        model = Profile
        exclude = ['user','photo']
        read_only_fields = ['id','role']
    def get_photo_url(self,obj):return f'/api/profiles/{obj.user_id}/photo/?v={obj.photo.name.rsplit("/",1)[-1]}' if obj.photo else None
    def get_page_url(self,obj):return '/talent/'+obj.page_slug+'/' if obj.page_slug and obj.published and obj.role=='worker' else None
    def validate_page_slug(self,value):
        value=(value or '').strip().lower() or None
        if value and Profile.objects.filter(page_slug=value).exclude(pk=getattr(self.instance,'pk',None)).exists():raise serializers.ValidationError('That profile address is already taken.')
        return value
    def validate(self, data):
        from .catalog import CATALOG
        for field in ['name','location','headline','bio']:
            if field in data: data[field] = data[field].strip()
        if 'professions' in data:
            if not isinstance(data['professions'],list) or len(data['professions'])>10:
                raise serializers.ValidationError({'professions':'Choose up to 10 professions.'})
            for p in data['professions']:
                if not isinstance(p,dict) or not p.get('profession') or not p.get('category'):
                    raise serializers.ValidationError({'professions':'Each profession needs a category and profession name.'})
                if p['profession'] not in CATALOG.get(p['category'],{}):
                    raise serializers.ValidationError({'professions':'Choose a profession from its listed category.'})
                p['skills'] = string_list(p.get('skills',[]),'skills')
                if 'experience' in p and (not isinstance(p['experience'],int) or p['experience']<0 or p['experience']>70):
                    raise serializers.ValidationError({'professions':'Profession experience must be between 0 and 70 years.'})
        if 'work_history' in data:
            if not isinstance(data['work_history'],list) or len(data['work_history'])>20:
                raise serializers.ValidationError({'work_history':'Use up to 20 experience entries.'})
            for entry in data['work_history']:
                if not isinstance(entry,dict) or not str(entry.get('title','')).strip() or not str(entry.get('organisation','')).strip():
                    raise serializers.ValidationError({'work_history':'Each experience needs a role and organisation.'})
        if 'projects' in data:
            if not isinstance(data['projects'],list) or len(data['projects'])>20:
                raise serializers.ValidationError({'projects':'Use up to 20 projects.'})
            for p in data['projects']:
                if not isinstance(p,dict) or not str(p.get('title','')).strip():
                    raise serializers.ValidationError({'projects':'Every project needs a title.'})
                if p.get('url'):
                    serializers.URLField().run_validation(p['url'])
                images=p.get('image_ids',[])
                if not isinstance(images,list) or len(images)>6 or any(type(i) is not int for i in images):
                    raise serializers.ValidationError({'projects':'Each project can have up to six uploaded images.'})
                if images:
                    owner=self.instance.user if self.instance else self.context['request'].user
                    if ProjectImage.objects.filter(owner=owner,pk__in=images).count()!=len(set(images)):
                        raise serializers.ValidationError({'projects':'Only your own uploaded images can be attached.'})
        if 'work_types' in data:
            data['work_types'] = string_list(data['work_types'],'work_types')
            if any(x not in ['gig','full_time','part_time','internship'] for x in data['work_types']):
                raise serializers.ValidationError({'work_types':'Choose a supported opportunity type.'})
        instance = self.instance
        value = lambda k: data.get(k,getattr(instance,k,None))
        if value('published'):
            for field in ['name','headline','location','professions','work_types']:
                if not value(field): raise serializers.ValidationError({field:'Required before publishing your profile.'})
            if any(not p.get('skills') for p in value('professions')):
                raise serializers.ValidationError({'professions':'Add at least one skill per profession.'})
        return data


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        exclude = ['owner']
        read_only_fields = ['status','review_note']
    def validate(self,data):
        from .catalog import CATALOG
        if 'industry' in data and data['industry'] not in CATALOG:
            raise serializers.ValidationError({'industry':'Choose one of the listed profession categories.'})
        for k in ['name','industry','location','registration_number']:
            if k in data and not data[k].strip(): raise serializers.ValidationError({k:'This field is required.'})
        return data


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        exclude = ['owner','file']
        read_only_fields = ['status','created_at','review_note']


class OpportunitySerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.name',read_only=True)
    business_verified = serializers.SerializerMethodField()
    interest_count = serializers.IntegerField(source='interests.count',read_only=True)
    shortlist_count = serializers.IntegerField(source='shortlists.count',read_only=True)
    class Meta:
        model = Opportunity
        fields = '__all__'
        read_only_fields = ['business','created_at']
    def get_business_verified(self,obj): return obj.business.status == 'approved'
    def validate(self,data):
        for field in ['title','description','profession','location','deliverables']:
            if field in data and not data[field].strip(): raise serializers.ValidationError({field:'This field is required.'})
        for field in ['skills','preferred_skills']:
            if field in data: data[field] = string_list(data[field],field)
        if 'skills' in data and not data['skills']: raise serializers.ValidationError({'skills':'Select at least one required skill.'})
        start = data.get('start_date',getattr(self.instance,'start_date',None))
        end = data.get('end_date',getattr(self.instance,'end_date',None))
        if start and end and end < start: raise serializers.ValidationError({'end_date':'End date must be on or after start date.'})
        return data


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        exclude = ['provider_id']


class ReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.profile.name',read_only=True)
    class Meta:
        model = Review
        fields = ['id','author','author_name','rating','comment','created_at']
        read_only_fields = ['author','created_at']


class SubmissionAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model=SubmissionAttachment
        fields=['id','name','kind','size','created_at','submission']


class WorkSubmissionSerializer(serializers.ModelSerializer):
    attachments=SubmissionAttachmentSerializer(many=True,read_only=True)
    class Meta:
        model=WorkSubmission
        fields=['id','notes','links','attachments','created_at']


class EngagementSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.profile.name',read_only=True)
    business_name = serializers.CharField(source='opportunity.business.name',read_only=True)
    title = serializers.CharField(source='opportunity.title',read_only=True)
    employer_id = serializers.IntegerField(source='opportunity.business.owner_id',read_only=True)
    payments = PaymentSerializer(many=True,read_only=True)
    reviews = serializers.SerializerMethodField()
    submissions=WorkSubmissionSerializer(many=True,read_only=True)
    class Meta:
        model = Engagement
        fields = '__all__'
    def get_reviews(self,obj):
        reviews = list(obj.reviews.all())
        request = self.context.get('request')
        visible = reviews if len(reviews)>=2 else [r for r in reviews if request and r.author_id==request.user.id]
        return ReviewSerializer(visible,many=True).data


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=Notification
        fields=['id','category','title','message','target','read_at','created_at']


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model=NotificationPreference
        exclude=['id','user']
