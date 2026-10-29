from django.contrib import admin
from .models import Profile,Business,Document,Opportunity,Interest,Shortlist,Engagement,Review,Payment,Notification,NotificationPreference,EmailDelivery,AdminAudit

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display=['name','industry','location','status','owner']
    list_filter=['status']
    search_fields=['name','registration_number']
    actions=['approve','request_changes']
    @admin.action(description='Approve selected businesses')
    def approve(self,request,queryset):
        for obj in queryset:
            obj.status='approved';obj.review_note='Business documents reviewed by admin.';obj.save()
    @admin.action(description='Request changes')
    def request_changes(self,request,queryset):
        for obj in queryset:
            obj.status='changes';obj.review_note='Please review and update your business documents.';obj.save()

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display=['title','owner','kind','profession','skill','status','expires']
    list_filter=['kind','status']
    exclude=['file']
    readonly_fields=['private_download']
    def private_download(self,obj):
        from django.utils.html import format_html
        return format_html('<a href="/api/documents/{}/download/">Download private document</a>',obj.pk) if obj.pk else 'Upload through the app.'

@admin.register(Engagement)
class EngagementAdmin(admin.ModelAdmin):
    list_display=['id','worker','opportunity','status','payment_mode']
    list_filter=['status']
    readonly_fields=['worker','opportunity','agreed_amount','agreed_deliverables','agreed_start','agreed_end','payment_mode']

admin.site.register([Profile,Opportunity,Interest,Shortlist,Review])
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display=['reference','amount','mode','status','created_at']
    readonly_fields=['engagement','reference','provider_id','amount','status','mode','created_at']
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False

admin.site.site_header='FLIP Gig House · Trust & Operations'
admin.site.site_title='FLIP Admin'
admin.site.index_title='Marketplace administration'

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display=['title','user','category','read_at','created_at']
    list_filter=['category']
    readonly_fields=['user','category','title','message','target','event_key','read_at','created_at']
    def has_add_permission(self,request):return False

@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display=['id','notification','status','attempts','provider_id','created_at']
    list_filter=['status']
    readonly_fields=['notification','status','attempts','provider_id','last_error','next_attempt','claimed_at','created_at']
    actions=['retry_confirmed_unsent']
    @admin.action(description='Retry failed emails after checking Gmail (excludes accepted or uncertain sends)')
    def retry_confirmed_unsent(self,request,queryset):
        from django.utils import timezone
        count=queryset.filter(status__in=['failed','retry']).update(status='queued',attempts=0,next_attempt=timezone.now(),last_error='')
        self.message_user(request,f'{count} failed/retry emails queued. Uncertain sends require provider reconciliation.')
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False

admin.site.register(NotificationPreference)

@admin.register(AdminAudit)
class AdminAuditAdmin(admin.ModelAdmin):
    list_display=['actor','action','record_type','record_id','created_at']
    readonly_fields=['actor','action','record_type','record_id','note','details','created_at']
    def has_add_permission(self,request):return False
    def has_delete_permission(self,request,obj=None):return False
