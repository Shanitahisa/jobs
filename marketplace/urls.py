from django.urls import path,include
from . import views
from . import workspace_views as workspace
urlpatterns=[
 path('people/',workspace.people),path('people/<int:pk>/',workspace.person),
 path('system/',include('marketplace.system_urls')),
 path('me/photo/',workspace.profile_photo),path('profiles/<int:user_id>/photo/',workspace.view_profile_photo),path('profiles/public/<slug:slug>/',workspace.public_profile),
 path('engagements/<int:pk>/attachments/',workspace.submission_attachments),path('submission-attachments/<int:pk>/',workspace.submission_attachment),path('payments/',workspace.payments),
 path('notifications/',views.notifications),path('notifications/read-all/',views.notifications_read_all),
 path('notifications/preferences/',views.notification_preferences),path('notifications/test-email/',views.notification_test_email),
 path('notifications/<int:pk>/',views.notification_read),
 path('project-images/',views.upload_project_image),path('project-images/<int:pk>/',views.project_image),
 path('interests/',views.interests),path('shortlists/',views.shortlists),
 path('payout-account/',views.payout_account),
 path('engagements/<int:pk>/sandbox-payout/',views.sandbox_payout),
 path('engagements/<int:pk>/verify-payout/',views.verify_payout),
 path('catalog/',views.catalog),path('auth/register/',views.register),path('auth/login/',views.login),path('auth/logout/',views.logout),path('me/',views.me),
 path('business/',views.business),path('business/submit/',views.submit_business),
 path('documents/',views.documents),path('documents/<int:pk>/download/',views.download_document),path('documents/<int:pk>/parse/',views.parse_cv),
 path('opportunities/',views.opportunities),path('opportunities/<int:pk>/',views.opportunity_detail),path('opportunities/<int:pk>/candidates/',views.candidates),
 path('opportunities/<int:pk>/interest/',views.express_interest),path('opportunities/<int:pk>/shortlist/<int:worker_id>/',views.shortlist),
 path('engagements/',views.engagements),path('engagements/<int:pk>/review/',views.review),path('engagements/<int:pk>/checkout/',views.checkout),path('engagements/<int:pk>/<str:action>/',views.engagement_action),
 path('payments/verify/',views.verify_payment),
]
