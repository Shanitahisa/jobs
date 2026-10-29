from django.db import migrations


def add_unique_email(apps,schema_editor):
    User=apps.get_model('auth','User')
    from django.db.models.functions import Lower
    from django.db.models import Count
    duplicates=User.objects.exclude(email='').annotate(normalized=Lower('email')).values('normalized').annotate(total=Count('id')).filter(total__gt=1)
    if duplicates.exists():raise RuntimeError('Resolve duplicate account email addresses before applying the unique-email migration.')
    schema_editor.execute("CREATE UNIQUE INDEX unique_account_email_ci ON auth_user (LOWER(email)) WHERE email <> ''")


def remove_unique_email(apps,schema_editor):
    schema_editor.execute('DROP INDEX unique_account_email_ci')


class Migration(migrations.Migration):
    dependencies=[('marketplace','0007_document_review_note_profile_page_slug_profile_photo_and_more')]
    operations=[migrations.RunPython(add_unique_email,remove_unique_email)]
