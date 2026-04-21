"""
Django settings for temp project.

For more information on this file, see
https://docs.djangoproject.com/en/stable/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/stable/ref/settings/
"""

import os

from typing import Any

import environ


# Build paths inside the project like this: os.path.join(PROJECT_DIR, ...)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(PROJECT_DIR)

# Initialize environ
env = environ.Env(
    AUTO_CONVERT_PDFS=(bool, False),
    GEMINI_API_KEY=(str, ""),
    WAGTAILADMIN_BASE_URL=(str, "http://localhost:8000"),
    PDF_CONVERSION_TIMEOUT_HOURS=(int, 3),
)

# Read .env file if it exists (will silently continue if it doesn't)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "not-a-secure-key"  # noqa: S105

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]


# Application definition
# https://docs.djangoproject.com/en/5.2/ref/settings/#installed-apps

LOCAL_APPS = [
    "tests.testproject.testapp",
]

THIRD_PARTY_APPS = [
    # wagtail_pdf_converter is loaded before wagtail.admin (in WAGTAIL_APPS)
    # to allow it to override default admin views/URLs.
    "wagtail_pdf_converter",
]

WAGTAIL_APPS = [
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
]

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
]

OTHER_THIRD_PARTY_APPS = [
    "wagtailmarkdown",
    "django_tasks",
    "django_extensions",
]

INSTALLED_APPS = LOCAL_APPS + THIRD_PARTY_APPS + WAGTAIL_APPS + DJANGO_APPS + OTHER_THIRD_PARTY_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "tests.testproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


# Using DatabaseCache to make sure that the cache is cleared between tests.
# This prevents false-positives in some wagtail core tests where we are
# changing the 'wagtail_root_paths' key which may cause future tests to fail.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache",
    }
}


# don't use the intentionally slow default password hasher
PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)


# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases

DATABASES = {
    "default": env.db(default="sqlite:///test_wagtail_pdf_converter.db"),
}

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = "en-gb"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# this is where Django *looks for* static files
STATICFILES_DIRS = [os.path.join(BASE_DIR, "tests", "testproject", "static")]

# this is where static files are *collected*
STATIC_ROOT = os.path.join(BASE_DIR, "tests", "testproject", "staticfiles")

# this is the *URL* for static files
STATIC_URL = "/static/"

MEDIA_ROOT = os.path.join(BASE_DIR, "tests", "testproject", "media")


# Wagtail settings

WAGTAIL_SITE_NAME = "PDF Converter test site"
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL")

# https://docs.wagtail.io/en/stable/advanced_topics/documents/custom_document_model.html
WAGTAILDOCS_DOCUMENT_MODEL = "testapp.CustomDocument"
WAGTAILDOCS_DOCUMENT_FORM_BASE = "wagtail_pdf_converter.forms.PDFConverterDocumentForm"

# Wagtail Markdown Configuration
# Configure extensions and settings for rendering PDF-converted markdown content
WAGTAILMARKDOWN = {
    # Extensions configuration
    "extensions": [
        "tables",  # Support for tables
        "fenced_code",  # Support for code blocks
        "def_list",  # Support for definition lists
        "footnotes",  # Support for footnotes
        "toc",  # Table of contents support
        "attr_list",  # Support for attributes on elements
        "md_in_html",  # Support for markdown inside HTML
        "codehilite",  # Syntax highlighting support
        "sane_lists",  # Better list handling
        "wagtail_pdf_converter.markdown_extensions",  # Wrap headings with IDs in anchor links
    ],
    "extension_configs": {
        "footnotes": {
            "UNIQUE_IDS": True,  # Ensure unique footnote IDs
        },
        "toc": {
            "permalink": False,  # No pilcrow symbols needed
            "anchorlink": False,  # Don't make headings clickable - keep them as plain text
            "anchorlink_class": "heading",  # Use site's heading class
            "toc_depth": "2-3",  # Include h2 and h3 only
            "title": "Contents",  # Add a title to the TOC
            "toc_class": "section__nav",
        },
        "codehilite": {
            "css_class": "codehilite",
            "use_pygments": True,
        },
    },
    # Settings mode - extend the defaults rather than override
    "allowed_settings_mode": "extend",
    "extensions_settings_mode": "extend",
    # Tab length for proper formatting
    "tab_length": 4,
    # Custom allowed tags for PDF conversion content
    "allowed_tags": [
        "div",  # For structure and chart descriptions
        "blockquote",  # For quotes and highlighted sections
        "del",  # For strikethrough (deletions)
        "ins",  # For insertions
        "mark",  # For highlighted text
        "sup",  # For superscript (footnotes)
        "sub",  # For subscript
        "span",  # For inline styling
        "img",  # For images from PDF conversion
        "figure",  # For image figures
        "figcaption",  # For image captions
        "section",  # For document sections
        "aside",  # For sidebar content
        "strong",  # For bold text
        "em",  # For italic text
        "code",  # For inline code
        "pre",  # For code blocks
    ],
    "allowed_attributes": {
        "a": ["href", "title", "id", "class"],
        "h1": ["id", "class"],
        "h2": ["id", "class"],
        "h3": ["id", "class"],
        "h4": ["id", "class"],
        "h5": ["id", "class"],
        "h6": ["id", "class"],
        "div": ["class", "id", "markdown"],
        "blockquote": ["class", "id", "markdown"],
        "del": ["class"],
        "ins": ["class"],
        "mark": ["class"],
        "span": ["class", "id"],
        "img": ["src", "alt", "title", "class", "width", "height"],
        "figure": ["class"],
        "figcaption": ["class"],
        "section": ["class", "id", "markdown"],
        "aside": ["class", "id", "markdown"],
        "table": ["class"],
        "thead": ["class"],
        "tbody": ["class"],
        "tr": ["class"],
        "th": ["class", "scope"],
        "td": ["class"],
        "ol": [
            "type",
            "class",
            "markdown",
        ],  # Support alphabetical lists and markdown content in list items
        "ul": ["class", "markdown"],  # Support markdown content in list items
        "li": ["class"],
        "pre": ["class"],
        "code": ["class"],
    },
}

# Background tasks settings

# TASKS: dict[str, dict[str, Any]] = {
#     "default": {
#         "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
#         "ENQUEUE_ON_COMMIT": False,
#     },
#     "pdf_conversion": {
#         "BACKEND": "django_tasks.backends.database.DatabaseBackend",
#     },
# }

# In tests, we want all tasks, including the PDF conversion ones,
# to run immediately and synchronously for predictable results.
TASKS: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        "ENQUEUE_ON_COMMIT": False,
    },
    "pdf_conversion": {
        "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        "ENQUEUE_ON_COMMIT": False,
    },
}

# PDF Transformation settings
WAGTAIL_PDF_CONVERTER = {
    "AI_BACKENDS": {
        "default": {
            "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
            "CONFIG": {
                "API_KEY": env("GEMINI_API_KEY"),
            },
        }
    },
    "AUTO_CONVERT_PDFS": env("AUTO_CONVERT_PDFS"),
    "PDF_CONVERSION_TIMEOUT_HOURS": env("PDF_CONVERSION_TIMEOUT_HOURS", 3),
    "ENABLE_ADMIN_EXTENSIONS": True,
}
