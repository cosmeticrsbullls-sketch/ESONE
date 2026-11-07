import unittest
from html.parser import HTMLParser
from modules.button_icons import action_key,decorate_controls,svg,PATHS,CSS
from modules.ui import enhance,icon

class ButtonIconTests(unittest.TestCase):
    def test_action_meanings(self):
        for label,key in [('Sales','sales'),('Collection','collection'),('Demo','demo'),('Book Order','order'),('Punch In','in'),('Punch Out','out'),('Share','share'),('Download PDF','download'),('Save Client','save'),('Edit educator','edit'),('Delete','delete'),('Search','search'),('Import bills and previous collections','add')]:
            with self.subTest(label=label):self.assertEqual(action_key(label),key)

    def test_form_and_script_bytes_are_preserved(self):
        source='<form method="post" action="/save"><input name="csrf" value="not-a-real-token"><button name="action" value="save">Save &amp; Continue</button></form><script>const label="<button>Delete</button>";</script>'
        result=decorate_controls(source)
        self.assertEqual(result,source.replace('value="save">','value="save" data-action-icon="save">'))

    def test_dynamic_labels_keep_icon_attribute(self):
        source='<button type="button" class="share-pdf">Share</button>'
        result=decorate_controls(source)
        # textContent replacement leaves the decoration on the control itself.
        self.assertIn('data-action-icon="share"',result.replace('>Share<','>Preparing PDF…<'))

    def test_existing_graphics_and_brand_are_not_duplicated(self):
        source='<a class="esone-brand" href="/workspace">ESONE</a><a href="/workspace">'+icon('dashboard')+'Home</a><button aria-label="Close"><svg></svg></button><a href="/x"><img src="x">Client</a>'
        self.assertEqual(decorate_controls(source),source)

    def test_idempotent_and_entities_preserved(self):
        source='<a href="/report?a=1&amp;b=2">Daily &amp; Monthly Reports</a>'
        result=decorate_controls(source)
        self.assertIn('data-action-icon="reports"',result)
        self.assertEqual(decorate_controls(result),result)
        self.assertIn('href="/report?a=1&amp;b=2"',result)

    def test_main_and_login_controls_are_decorated(self):
        for signed_in,path,label in [(True,'/workspace','Punch Out'),(False,'/','Login')]:
            html='<html><head></head><body><main><button>'+label+'</button></main></body></html>'
            rendered=enhance(html,path,signed_in=signed_in)
            self.assertIn('data-action-icon="'+('out' if signed_in else 'in')+'"',rendered)
            self.assertIn('esone.css?v=7',rendered)

    def test_svg_assets_are_valid_and_duotone(self):
        from xml.etree import ElementTree
        for key in PATHS:
            ElementTree.fromstring(svg(key))
            self.assertIn('#c99a39',svg(key))
        self.assertIn('[data-action-icon]::before',CSS)
        self.assertIn('@media(max-width:480px)',CSS)

    def test_plain_links_and_multiline_controls(self):
        source='<a href="/">← Home</a>\n<button\n type="submit">\nConfirm\n</button><a>No URL</a>'
        result=decorate_controls(source)
        self.assertIn('data-action-icon="home"',result)
        self.assertIn('data-action-icon="check"',result)
        self.assertIn('<a>No URL</a>',result)

if __name__=='__main__':unittest.main()
