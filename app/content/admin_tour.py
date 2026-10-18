"""Shelf studio guided tour: steps per admin page, shown on a staff member's first sign-ins."""

TOUR_SIGN_INS = 5

# Admin endpoint -> tour page key.
TOUR_PAGES = {
    'admin.dashboard': 'dashboard',
    'admin.books': 'books',
    'admin.edit_book': 'editor',
    'admin.categories': 'genres',
    'admin.orders': 'orders',
    'admin.enquiries': 'enquiries',
    'admin.staff': 'staff',
}

# Steps without a target open as a centred card. Steps whose target is missing
# for the current role or page state are skipped in the browser.
TOURS = {
    'dashboard': [
        {'kind': 'welcome', 'title': 'Welcome to Shelf studio.',
         'text': 'Let’s take a one-minute look around, from publishing your first audiobook to keeping track of orders. You can skip at any time.'},
        {'target': 'sidebar', 'title': 'Everything lives here.',
         'text': 'Every area of the studio is in this menu. The page you are on is highlighted.'},
        {'target': 'stats', 'title': 'Your shelf at a glance.',
         'text': 'Revenue, titles, drafts, orders and listener activity update as your store grows.'},
        {'target': 'add-book', 'title': 'Add an audiobook.',
         'text': 'Start here to create a new title. Save it as a draft and come back to it whenever you like.'},
        {'target': 'nav-books', 'title': 'Manage your catalogue.',
         'text': 'Edit, preview and filter every title, including Featured books that are Coming soon.'},
        {'target': 'nav-categories', 'title': 'Organise with genres.',
         'text': 'Genres power the storefront filters and the homepage genre tiles.'},
        {'target': 'nav-orders', 'title': 'Orders and listening access.',
         'text': 'Check payments, revoke or restore access, and resend a customer’s listening link.'},
        {'target': 'nav-enquiries', 'title': 'Production enquiries.',
         'text': 'Authors and publishers who contact you land here. Update their status and keep private notes.'},
        {'target': 'nav-staff', 'title': 'Your team.',
         'text': 'Add editors and support staff, each with the right permissions.'},
        {'target': 'storefront', 'title': 'See what listeners see.',
         'text': 'Open the public storefront in one click to check your changes.'},
        {'kind': 'finish', 'target': 'tour-button', 'title': 'You’re all set.',
         'text': 'Replay this guide for any page from here. Each page has its own short tour the first time you open it.'},
    ],
    'books': [
        {'target': 'add-book', 'title': 'Add a new title.',
         'text': 'Create an audiobook. Only the title and author are needed to save a draft.'},
        {'target': 'book-search', 'title': 'Find any title.',
         'text': 'Search by title. Reset clears the search.'},
        {'target': 'book-views', 'title': 'Filter by shelf.',
         'text': 'Switch between all titles, Featured books, and Coming soon books that are waiting for a price.'},
        {'kind': 'finish', 'target': 'book-table', 'title': 'Your titles.',
         'text': 'See each book’s state, price and collections. Use Edit to change details, add a price or upload audio, and Preview to see its storefront page.'},
    ],
    'editor': [
        {'target': 'editor-details', 'title': 'Start with the basics.',
         'text': 'Title and author are required. A clear description helps listeners decide.'},
        {'target': 'editor-media', 'title': 'Cover and audio.',
         'text': 'Upload a cover, a preview of up to 60 seconds and the full audiobook, or add chapters one at a time. Duration is calculated for you.'},
        {'target': 'editor-price', 'title': 'Set a price, or not yet.',
         'text': 'Enter a price in pounds to sell the book. Leave it blank to announce it first.'},
        {'target': 'editor-featured', 'title': 'Featured and Coming soon.',
         'text': 'Tick Featured with no price and the book appears on the Featured page as Coming soon. Add a price later to open sales.'},
        {'target': 'editor-genres', 'title': 'Pick its genres.',
         'text': 'Choose at least one genre so listeners can find the book.'},
        {'target': 'editor-publication', 'title': 'Draft, publish or archive.',
         'text': 'Keep it as a Draft while you work. Choose Published when ready, and the studio lists anything still missing. Archived hides a title.'},
        {'target': 'editor-preview', 'title': 'Preview before it goes live.',
         'text': 'See the exact storefront page, with purchase buttons disabled.'},
        {'kind': 'finish', 'target': 'editor-save', 'title': 'Save your work.',
         'text': 'If anything needs fixing, a summary at the top links straight to each field. Select upload files again after an error.'},
    ],
    'genres': [
        {'target': 'genre-form', 'title': 'Add a genre.',
         'text': 'Type a name and add it. It becomes available in the book editor immediately.'},
        {'kind': 'finish', 'target': 'genre-list', 'title': 'Your genres.',
         'text': 'These appear in the storefront filters and the homepage genre tiles.'},
    ],
    'orders': [
        {'kind': 'finish', 'target': 'order-table', 'title': 'Every checkout.',
         'text': 'Open an order to see its titles, payment status and listener access. From there you can revoke, restore or resend access, with a reason recorded.'},
    ],
    'enquiries': [
        {'target': 'enquiry', 'title': 'A production enquiry.',
         'text': 'Project details, contact information and any manuscript the author attached.'},
        {'kind': 'finish', 'target': 'enquiry-form', 'title': 'Track each conversation.',
         'text': 'Move the status from New to Closed and keep private notes for your team.'},
    ],
    'staff': [
        {'target': 'staff-table', 'title': 'Your team.',
         'text': 'Disable an account to sign that person out everywhere immediately.'},
        {'kind': 'finish', 'target': 'staff-form', 'title': 'Add a team member.',
         'text': 'Owners manage everything. Editors manage books, genres and enquiries. Support manages orders, access and enquiries.'},
    ],
}
