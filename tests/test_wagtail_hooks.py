from http import HTTPStatus
from importlib import reload
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from django.core.files.images import ImageFile
from django.test import override_settings
from django.urls import clear_url_caches, reverse
from PIL import Image as PILImage
from wagtail import hooks
from wagtail.images import get_image_model
from wagtail.models import Collection

from tests.testproject import urls
from wagtail_pdf_converter.conf import settings
from wagtail_pdf_converter.constants import EXTRACTED_IMAGES_COLLECTION_NAME


@pytest.mark.django_db
class TestRegisterAdminUrls:
    """Test the register_admin_urls hook."""

    def test_base_urls_always_registered(self):
        """Test that base package URLs are always registered."""
        # Get the hook function
        hook_fns = hooks.get_hooks("register_admin_urls")
        register_admin_urls = None
        for fn in hook_fns:
            if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks":
                register_admin_urls = fn
                break

        assert register_admin_urls is not None, "register_admin_urls hook not found"

        urlpatterns = register_admin_urls()

        # Check that we have at least the base wagtail_pdf_converter namespace
        assert len(urlpatterns) >= 1
        assert any("wagtail_pdf_converter" in str(pattern) for pattern in urlpatterns)

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": False, "FILTER_PDF_IMAGES": False})
    def test_custom_document_index_not_registered_when_disabled(self):
        """Test that CustomDocumentIndexView URLs are not registered when setting is False."""
        settings.reload()

        hook_fns = hooks.get_hooks("register_admin_urls")
        register_admin_urls = None
        for fn in hook_fns:
            if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks":
                register_admin_urls = fn
                break

        urlpatterns = register_admin_urls()

        # Check that documents/ override is NOT in the patterns
        # The only pattern should be wagtail_pdf_converter/
        assert len(urlpatterns) == 1

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": True, "FILTER_PDF_IMAGES": False})
    def test_custom_document_index_registered_when_enabled(self):
        """Test that CustomDocumentIndexView URLs are registered when setting is True."""
        settings.reload()

        hook_fns = hooks.get_hooks("register_admin_urls")
        register_admin_urls = None
        for fn in hook_fns:
            if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks":
                register_admin_urls = fn
                break

        urlpatterns = register_admin_urls()

        # Should have 3 patterns: wagtail_pdf_converter/, documents/, documents/results/
        assert len(urlpatterns) == 3

        # Check that documents/ and documents/results/ are present
        pattern_strings = [str(pattern.pattern) for pattern in urlpatterns]
        assert any("documents/" in p and "results" not in p for p in pattern_strings)
        assert any("documents/results/" in p for p in pattern_strings)

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": False})
    def test_image_index_not_registered_when_filter_disabled(self):
        """Image override URLs absent when FILTER_PDF_IMAGES is False."""
        settings.reload()

        hook_fns = hooks.get_hooks("register_admin_urls")
        register_admin_urls = next(fn for fn in hook_fns if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks")

        urlpatterns = register_admin_urls()
        pattern_strings = [str(p.pattern) for p in urlpatterns]
        assert not any("images/" in p for p in pattern_strings)

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_image_index_registered_when_filter_enabled(self):
        """images/ and images/results/ override URLs present when FILTER_PDF_IMAGES is True."""
        settings.reload()

        hook_fns = hooks.get_hooks("register_admin_urls")
        register_admin_urls = next(fn for fn in hook_fns if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks")

        urlpatterns = register_admin_urls()
        pattern_strings = [str(p.pattern) for p in urlpatterns]
        assert any("images/" in p and "results" not in p for p in pattern_strings)
        assert any("images/results/" in p for p in pattern_strings)


@pytest.mark.django_db
class TestRegisterAdminMenuItems:
    """Test the register_admin_menu_item hook."""

    def test_conversion_metrics_menu_item_registered(self):
        """Test that the Conversion Metrics menu item is registered."""
        hook_fns = hooks.get_hooks("register_admin_menu_item")
        menu_items = [fn() for fn in hook_fns if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks"]

        assert len(menu_items) >= 1
        metrics_item = menu_items[0]
        assert metrics_item.label == "Conversion Metrics"
        assert metrics_item.icon_name == "doc-full"
        assert metrics_item.order == 10000


@pytest.mark.django_db
class TestGlobalAdminCss:
    """Test the insert_global_admin_css hook."""

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": False})
    def test_no_css_when_extensions_disabled(self):
        """Test that no CSS is inserted when admin extensions are disabled."""
        settings.reload()
        hook_fns = hooks.get_hooks("insert_global_admin_css")
        css_fns = [fn for fn in hook_fns if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks"]

        assert len(css_fns) >= 1
        css_output = css_fns[0]()
        assert css_output == ""

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": True})
    def test_css_inserted_when_extensions_enabled(self):
        """Test that CSS is inserted when admin extensions are enabled."""
        settings.reload()
        hook_fns = hooks.get_hooks("insert_global_admin_css")
        css_fns = [fn for fn in hook_fns if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks"]

        assert len(css_fns) >= 1
        css_output = css_fns[0]()
        assert css_output != ""
        assert "wagtail_pdf_converter/css/admin.css" in css_output
        assert '<link rel="stylesheet"' in css_output


@pytest.mark.django_db
class TestCustomDocumentIndexViewIntegration:
    """Integration tests for CustomDocumentIndexView when enabled."""

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": True})
    def test_custom_index_view_accessible(self, client_superuser):
        """Test that the custom document index view is accessible when enabled."""
        # This tests the actual URL resolution and view rendering
        # We need to reload URLs for the override_settings to take effect
        settings.reload()
        clear_url_caches()
        reload(urls)

        url = reverse("wagtaildocs:index")
        response = client_superuser.get(url)

        # Should successfully load the custom view
        assert response.status_code == HTTPStatus.OK

    @override_settings(WAGTAIL_PDF_CONVERTER={"ENABLE_ADMIN_EXTENSIONS": True})
    def test_custom_index_results_view_accessible(self, client_superuser):
        """Test that the custom document index results view is accessible when enabled."""
        settings.reload()
        clear_url_caches()
        reload(urls)

        url = reverse("wagtaildocs:index_results")
        response = client_superuser.get(url)

        # Should successfully load the custom results view
        assert response.status_code == HTTPStatus.OK


def _make_chooser_request(collection_id=None):
    req = MagicMock()
    req.GET = {"collection_id": str(collection_id)} if collection_id is not None else {}
    return req


def _make_image_file():
    buf = BytesIO()
    PILImage.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    buf.seek(0)
    return ImageFile(buf, name="test.png")


def _create_test_image(title, collection):
    Image = get_image_model()
    img = Image(title=title, file=_make_image_file(), collection=collection)
    img._set_file_hash()
    img.save()
    return img


def _get_chooser_hook():
    """Return the package's construct_image_chooser_queryset hook function."""
    hook_fns = hooks.get_hooks("construct_image_chooser_queryset")
    for fn in hook_fns:
        if fn.__module__ == "wagtail_pdf_converter.wagtail_hooks":
            return fn
    raise AssertionError("construct_image_chooser_queryset hook not registered")


@pytest.mark.django_db
class TestImageChooserQuerysetHook:
    def _setup_images(self):
        root = Collection.get_first_root_node()
        pdf_col = root.add_child(name=EXTRACTED_IMAGES_COLLECTION_NAME)
        other_col = root.add_child(name="Editorial")
        pdf_img = _create_test_image("PDF img", pdf_col)
        other_img = _create_test_image("Other img", other_col)
        return pdf_col, pdf_img, other_img

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_excludes_pdf_images_when_setting_on_no_collection_filter(self):
        """FILTER_PDF_IMAGES=True, no collection_id → PDF images excluded."""
        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        Image = get_image_model()
        hook = _get_chooser_hook()

        result = hook(Image.objects.all(), _make_chooser_request())

        ids = list(result.values_list("id", flat=True))
        assert other_img.id in ids
        assert pdf_img.id not in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_shows_all_when_setting_on_collection_filter_present(self):
        """FILTER_PDF_IMAGES=True, collection_id present → all images shown."""
        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        Image = get_image_model()
        hook = _get_chooser_hook()

        result = hook(Image.objects.all(), _make_chooser_request(collection_id=pdf_col.id))

        ids = list(result.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": False})
    def test_shows_all_when_setting_off_no_collection_filter(self):
        """FILTER_PDF_IMAGES=False, no collection_id → all images shown (no filtering)."""
        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        Image = get_image_model()
        hook = _get_chooser_hook()

        result = hook(Image.objects.all(), _make_chooser_request())

        ids = list(result.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": False})
    def test_shows_all_when_setting_off_collection_filter_present(self):
        """FILTER_PDF_IMAGES=False, collection_id present → all images shown."""
        settings.reload()
        pdf_col, pdf_img, other_img = self._setup_images()
        Image = get_image_model()
        hook = _get_chooser_hook()

        result = hook(Image.objects.all(), _make_chooser_request(collection_id=pdf_col.id))

        ids = list(result.values_list("id", flat=True))
        assert pdf_img.id in ids
        assert other_img.id in ids


@pytest.mark.django_db
class TestCustomImageIndexViewIntegration:
    """Integration test: CustomImageIndexView served at /admin/images/ when enabled."""

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_image_index_accessible(self, client_superuser):
        settings.reload()
        clear_url_caches()
        reload(urls)

        url = reverse("wagtailimages:index")
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.OK

    @override_settings(WAGTAIL_PDF_CONVERTER={"FILTER_PDF_IMAGES": True})
    def test_image_index_results_accessible(self, client_superuser):
        settings.reload()
        clear_url_caches()
        reload(urls)

        url = reverse("wagtailimages:index_results")
        response = client_superuser.get(url)

        assert response.status_code == HTTPStatus.OK
