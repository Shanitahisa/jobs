from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from marketplace.models import Profile,Business,Opportunity,Interest,Shortlist,Document
from django.core.files.base import ContentFile

PASSWORD='FlipDemo!2026'


class Command(BaseCommand):
    help='Create fictional, repeatable demo records. Does not overwrite existing users or opportunities.'
    def handle(self,*args,**kwargs):
        def user(email,name,role,**fields):
            obj,created=User.objects.get_or_create(username=email,defaults={'email':email})
            if created:obj.set_password(PASSWORD);obj.save()
            profile,_=Profile.objects.get_or_create(user=obj,defaults={'name':name,'role':role,**fields})
            return obj
        employer=user('employer@flip.demo','Alex Morgan','employer',headline='Building teams that make things happen',location='Kampala')
        business,_=Business.objects.get_or_create(owner=employer,defaults={'name':'Studio North · Demo','industry':'Creative & Media','location':'Kampala','registration_number':'FICTIONAL-2026-001','description':'A fictional Kampala creative studio bringing brands and communities together. All opportunities are demonstration data.','status':'approved'})
        people=[
            ('amina@flip.demo','Amina Nakato','AN','Photographer','Creative & Media',['Photography','Event photography','Photo editing','Adobe Lightroom','Videography'],3,'Kampala','immediately',180000,'Photographer. Storyteller. Moment catcher.'),
            ('daniel@flip.demo','Daniel Okello','DO','Photographer','Creative & Media',['Photography','Event photography','Photo editing','Adobe Lightroom'],2,'Kampala','weekdays',150000,'Real people. Unforgettable frames.'),
            ('sarah@flip.demo','Sarah Namuli','SN','Graphic Designer','Creative & Media',['Graphic design','Typography','Adobe Photoshop','Adobe Illustrator','Social media design','Brand identity'],4,'Kampala','immediately',200000,'Turning bold ideas into visual identities.'),
            ('brian@flip.demo','Brian Ssemanda','BS','Web Developer','Technology',['React','TypeScript','Django','Python','PostgreSQL','HTML & CSS','UI design'],2,'Entebbe','evenings',250000,'Thoughtful interfaces. Reliable code.'),
            ('joan@flip.demo','Joan Achieng','JA','Event Assistant','Hospitality & Events',['Event coordination','Customer service','Communication','Teamwork','Registration'],1,'Kampala','weekends',80000,'Making every event feel effortless.'),
            ('moses@flip.demo','Moses Kato','MK','Accountant','Business & Finance',['Bookkeeping','Excel','QuickBooks','Financial reporting','Tax preparation'],5,'Jinja','immediately',180000,'Helping small businesses know their numbers.'),
        ]
        workers=[]
        for email,name,initials,profession,category,skills,years,location,availability,rate,headline in people:
            worker=user(email,name,'worker',headline=headline,bio=f'I am a fictional {profession.lower()} for the FLIP Africa Career Expo demonstration. I bring care, clear communication and practical experience to every project.',location=location,availability=availability,experience=years,rate=rate,published=True,work_types=['gig','part_time'],professions=[{'category':category,'profession':profession,'skills':skills}],projects=[{'title':'Community launch campaign','description':'A fictional project exploring local stories, teamwork and creative delivery.','url':''},{'title':'Independent portfolio study','description':'A personal project developing practical skills and a distinctive approach.','url':''}])
            workers.append(worker)
        today=timezone.localdate()
        saturday=today+timedelta(days=(5-today.weekday())%7 or 7)
        gigs=[
            {'title':'Capture the energy. Event photographer.','profession':'Photographer','skills':['Event photography','Photo editing','Adobe Lightroom'],'preferred_skills':['Videography'],'description':'We are bringing together young creatives for a fictional community launch in Ntinda. Capture the people, the details and the moments in between. This is a demo opportunity, not a genuine vacancy.','deliverables':'40 edited photographs and a selection of 10 social-ready images, delivered within 48 hours.','location':'Kampala','remote':False,'availability':'weekends','budget':250000,'start_date':saturday,'end_date':saturday,'minimum_experience':1},
            {'title':'A fresh identity for a fresh idea.','profession':'Graphic Designer','skills':['Graphic design','Adobe Illustrator','Brand identity'],'preferred_skills':['Typography'],'description':'Create a bold visual identity for a fictional youth-led coffee brand. Bring a clear point of view and a love for simple, expressive design. Demo only.','deliverables':'Logo concept, colour palette, type direction and three social media templates.','location':'Kampala','remote':True,'availability':'flexible','budget':650000,'start_date':today+timedelta(days=3),'end_date':today+timedelta(days=8),'minimum_experience':1},
            {'title':'Help make a community event happen.','profession':'Event Assistant','skills':['Event coordination','Communication','Teamwork'],'preferred_skills':['Registration'],'description':'Support guest registration and coordination at a fictional weekend creative meetup. Friendly communication and reliability matter. Demo only.','deliverables':'Support guest check-in, coordinate sessions and assist with event setup.','location':'Kampala','remote':False,'availability':'weekends','budget':100000,'start_date':saturday+timedelta(days=7),'end_date':saturday+timedelta(days=7),'minimum_experience':0},
            {'title':'Build something people love to use.','profession':'Web Developer','skills':['React','TypeScript','HTML & CSS'],'preferred_skills':['Django'],'description':'Build a responsive landing experience for a fictional local startup. Great for a developer who cares about small details. Demo only.','deliverables':'Responsive single-page website with accessible navigation and a documented handover.','location':'Kampala','remote':True,'availability':'evenings','budget':900000,'start_date':today+timedelta(days=5),'end_date':today+timedelta(days=12),'minimum_experience':1},
        ]
        for data in gigs:Opportunity.objects.get_or_create(business=business,title=data['title'],defaults=data)
        admin=user('admin@flip.demo','FLIP Administrator','employer')
        admin.is_staff=True;admin.is_superuser=True;admin.save()
        for kind,title in [('registration','Fictional business registration'),('licence','Fictional trading licence')]:
            if not Document.objects.filter(owner=employer,kind=kind).exists():
                doc=Document(owner=employer,kind=kind,title=title,status='verified')
                doc.file.save(kind+'-demo.txt',ContentFile('FICTIONAL DEMO DOCUMENT\nNot a genuine licence or registration.\nFLIP Africa Career Expo prototype.'))
        self.stdout.write(self.style.SUCCESS('Demo ready. Employer: employer@flip.demo | Worker: amina@flip.demo | Admin: admin@flip.demo | Password: '+PASSWORD))
