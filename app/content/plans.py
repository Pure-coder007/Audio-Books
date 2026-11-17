"""Author subscription plans: shown on /pricing, the production page and each author's account.

Prices are monthly, in pounds. Plans launch in February 2027; an author who signs up before then
reserves a plan, and their 14-day free trial starts on launch day.
"""

TRIAL_DAYS = 14
LAUNCH = 'February 2027'

PLANS = [
    dict(key='lite', name='Lite', price=19, tagline='For your first audiobook.',
         summary='One book at a time, planned from the whole manuscript.',
         features=['1 book project at a time',
                   'StoryDNA analysis of your whole manuscript',
                   'Story Intelligence Profile of characters, places and motifs',
                   'Sound recommendations you accept, change or reject',
                   'Email support']),
    dict(key='author', name='Author', price=39, tagline='For authors with a growing list.', popular=True,
         summary='Several books, with continuity checked across every chapter.',
         features=['Up to 3 book projects at a time',
                   'Everything in Lite',
                   'Audio Continuity Engine across every chapter',
                   'Classic narration or enhanced production planning',
                   'Your audiobook listed on the MyAudioShelf store']),
    dict(key='pro', name='Pro Author', price=79, tagline='For series and fuller productions.',
         summary='Dramatised, multi-voice and multilingual planning.',
         features=['Up to 10 book projects at a time',
                   'Everything in Author',
                   'Dramatised, multi-voice production planning',
                   'Translation planning for other-language editions',
                   'Priority review from the production team']),
    dict(key='publisher', name='Publisher', price=199, from_price=True, tagline='For publishers and imprints.',
         summary='A whole list, a whole team, one production memory.',
         features=['Book projects for your whole list',
                   'Everything in Pro Author',
                   'Team seats for editors and producers',
                   'Continuity across series and imprints',
                   'A named account manager and custom terms']),
]
PLAN_KEYS = {plan['key']: plan for plan in PLANS}
DEFAULT_PLAN = 'author'

FAQ = [
    ('When do the plans start?', f'Subscription plans launch in {LAUNCH}. Create your author account today to reserve a plan: your {TRIAL_DAYS}-day free trial starts on launch day.'),
    ('Do I need a card for the free trial?', f'No. The trial gives you every feature of your plan for {TRIAL_DAYS} days. We only ask for payment if you decide to continue, and you can cancel before the trial ends without paying anything.'),
    ('Can I change plan later?', 'Yes. Move up or down from your author account at any time. A Publisher plan is priced to the size of your list, so we agree it with you first.'),
    ('Who decides how my book sounds?', 'You do. The StoryDNA Engine reads the whole manuscript and recommends a treatment for each moment, and every recommendation waits for you to accept, change or reject it. Approved decisions become part of your book’s production memory.'),
    ('Do I keep the rights to my book?', 'Yes. Sending us your manuscript does not transfer your copyright. Anything to do with ownership of a finished recording, royalties or distribution is agreed with you in writing first.'),
    ('What if I want the studio to produce it for me?', 'Tell us about your book with the project form on the production page. The team will recommend an approach and talk you through the options.'),
]


def plan(key):
    return PLAN_KEYS.get(key) or PLAN_KEYS[DEFAULT_PLAN]
