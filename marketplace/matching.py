from django.utils import timezone
from .models import Document, Engagement


def match(profile, opportunity):
    skills = {s.casefold() for p in profile.professions for s in p.get('skills', [])}
    matched = [s for s in opportunity.skills if s.casefold() in skills]
    missing = [s for s in opportunity.skills if s.casefold() not in skills]
    reasons, blockers = [], []
    if opportunity.work_type not in profile.work_types: blockers.append('This work type is outside the worker’s stated preferences')
    else: reasons.append('Opportunity type matches the worker’s preferences')
    profession_ok = any(p.get('profession','').casefold() == opportunity.profession.casefold() for p in profile.professions)
    if not profession_ok: blockers.append('Different profession')
    if missing: blockers.append('Missing required skills: ' + ', '.join(missing))
    if matched: reasons.append(f'Has {len(matched)} of {len(opportunity.skills)} required skills: ' + ', '.join(matched))
    availability_ok = opportunity.availability == 'flexible' or profile.availability == 'immediately' or profile.availability == opportunity.availability
    if availability_ok: reasons.append('Availability fits the requested schedule')
    else: blockers.append('Availability does not fit the requested schedule')
    location_ok = opportunity.remote or profile.location.strip().casefold() == opportunity.location.strip().casefold()
    if location_ok: reasons.append('Remote work is supported' if opportunity.remote else f'Based in {profile.location}')
    else: blockers.append('Different on-site location')
    relevant = next((p for p in profile.professions if p.get('profession','').casefold()==opportunity.profession.casefold()),{})
    years = relevant.get('experience',profile.experience)
    experience_ok = years >= opportunity.minimum_experience
    if experience_ok: reasons.append(f'{years} years of relevant experience reported')
    else: blockers.append(f'Requires {opportunity.minimum_experience} years of experience')
    if opportunity.required_certificate:
        docs = Document.objects.filter(owner=profile.user,kind='certificate',skill='',profession__iexact=opportunity.profession,status='verified')
        if not any(d.expires is None or d.expires >= timezone.localdate() for d in docs):
            blockers.append('Verified, valid profession certificate required')
        else: reasons.append('Required profession certificate is verified')
    if opportunity.required_clearance:
        docs = Document.objects.filter(owner=profile.user,kind='clearance',profession__iexact=opportunity.profession,status='verified')
        if not any(d.expires is None or d.expires >= timezone.localdate() for d in docs):
            blockers.append('Verified, valid professional clearance required')
        else: reasons.append('Required professional clearance is verified; medical details stay private')
    if Engagement.objects.filter(worker=profile.user,status__in=['accepted','funded','submitted','approved'],agreed_start__lte=opportunity.end_date,agreed_end__gte=opportunity.start_date).exclude(opportunity=opportunity).exists():
        blockers.append('Dates overlap with an accepted engagement')
    preferred = [s for s in opportunity.preferred_skills if s.casefold() in skills]
    score = round(60 * len(matched) / max(len(opportunity.skills),1) + 20*availability_ok + 10*location_ok + 10*experience_ok)
    return {'score':score,'eligible':not blockers,'matched_skills':matched,'missing_skills':missing,'preferred_skills':preferred,'reasons':reasons,'blockers':blockers}
