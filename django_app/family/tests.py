from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from family.models import BulletinPost, Contact, ContactPerson, WishItem, WishList
from households.models import Household, Membership
from identity.models import User


class FamilyWishlistTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="ouder@example.com", email="ouder@example.com", password="safe-password-123", display_name="Ouder")
        self.child = User.objects.create_user(username="kind@example.com", email="kind@example.com", password="safe-password-123", display_name="Kind")
        self.household = Household.objects.create(name="Gezin")
        Membership.objects.create(household=self.household, user=self.parent, role=Membership.Role.PARENT)
        Membership.objects.create(household=self.household, user=self.child, role=Membership.Role.CHILD)
        self.client.force_login(self.parent)

    def test_parent_can_add_wish_to_child_list(self):
        response = self.client.post(reverse("family:add_wish"), {"owner_id": self.child.id, "title": "Nieuw boek", "price": "12.50"}, follow=True)
        self.assertEqual(response.status_code, 200)
        wishlist = WishList.objects.get(household=self.household, owner=self.child)
        self.assertTrue(WishItem.objects.filter(wishlist=wishlist, title="Nieuw boek").exists())

    def test_public_shared_wishlist_can_reserve_once(self):
        wishlist = WishList.objects.create(household=self.household, owner=self.child, title="Wensen", is_shared=True, share_token="public-token")
        item = WishItem.objects.create(household=self.household, wishlist=wishlist, title="Spel")
        public_url = reverse("family:public_wishlist", args=[wishlist.share_token])
        self.assertEqual(self.client.get(public_url).status_code, 200)
        reserve_url = reverse("family:reserve_wish", args=[wishlist.share_token, item.id])
        self.client.post(reserve_url, {"name": "Tante"})
        self.assertEqual(item.reservations.count(), 1)
        self.assertEqual(item.reservations.get().household_id, self.household.id)
        self.client.post(reserve_url, {"name": "Oom"})
        self.assertEqual(item.reservations.count(), 1)

    def test_vcard_import_and_export_keeps_contact_birthdays(self):
        vcard = b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Jan Jansen\r\nEMAIL:jan@example.com\r\nTEL:+31612345678\r\nADR;TYPE=HOME:;;Straat 1;Den Haag;;2511AA;NL\r\nBDAY:1990-05-14\r\nEND:VCARD\r\n"
        response = self.client.post(reverse("family:import_contacts"), {"file": SimpleUploadedFile("contact.vcf", vcard, content_type="text/vcard")}, follow=True)
        self.assertEqual(response.status_code, 200)
        contact = Contact.objects.get(household=self.household, name="Jan Jansen")
        self.assertEqual(contact.city, "Den Haag")
        self.assertEqual(ContactPerson.objects.get(contact=contact).birth_date.isoformat(), "1990-05-14")
        response = self.client.get(reverse("family:export_contacts"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/vcard; charset=utf-8")
        self.assertIn("BDAY:1990-05-14", response.content.decode())

    def test_parent_can_manage_contacts_people_wishes_and_posts(self):
        contact = Contact.objects.create(household=self.household, name="Familie Jansen", city="Utrecht")
        person = ContactPerson.objects.create(household=self.household, contact=contact, name="Jan Jansen")
        wishlist = WishList.objects.create(household=self.household, owner=self.child, title="Wensen")
        item = WishItem.objects.create(household=self.household, wishlist=wishlist, title="Boek")
        post = BulletinPost.objects.create(household=self.household, author=self.child, body="Oude mededeling")

        response = self.client.post(reverse("family:update_contact", args=[contact.id]), {
            "name": "Familie Jansen", "contact_type": "family", "email": "", "phone": "",
            "address": "Straat 1", "postal_code": "", "city": "Amersfoort", "notes": "",
        })
        self.assertRedirects(response, f"{reverse('family:index')}?tab=contacten")
        contact.refresh_from_db()
        self.assertEqual(contact.city, "Amersfoort")

        self.client.post(reverse("family:update_person", args=[person.id]), {
            "name": "Jan Jansen", "birth_date": "1990-05-14", "email": "jan@example.com", "phone": "",
        })
        person.refresh_from_db()
        self.assertEqual(person.birth_date.isoformat(), "1990-05-14")

        self.client.post(reverse("family:update_wish", args=[item.id]), {
            "title": "Nieuw boek", "url": "https://example.test/boek", "price": "19.95", "repeatable": "on",
        })
        item.refresh_from_db()
        self.assertEqual(item.title, "Nieuw boek")
        self.assertTrue(item.repeatable)

        response = self.client.post(reverse("family:delete_post", args=[post.id]))
        self.assertRedirects(response, f"{reverse('family:index')}?tab=prikbord")
        self.assertFalse(BulletinPost.objects.filter(pk=post.id).exists())

        self.client.post(reverse("family:delete_person", args=[person.id]))
        self.client.post(reverse("family:delete_wish", args=[item.id]))
        self.client.post(reverse("family:delete_contact", args=[contact.id]))
        self.assertFalse(ContactPerson.objects.filter(pk=person.id).exists())
        self.assertFalse(WishItem.objects.filter(pk=item.id).exists())
        self.assertFalse(Contact.objects.filter(pk=contact.id).exists())

    def test_child_cannot_manage_another_persons_wishlist_or_post(self):
        wishlist = WishList.objects.create(household=self.household, owner=self.parent, title="Wensen ouder")
        item = WishItem.objects.create(household=self.household, wishlist=wishlist, title="Privé wens")
        post = BulletinPost.objects.create(household=self.household, author=self.parent, body="Bericht van ouder")
        self.client.force_login(self.child)

        response = self.client.post(reverse("family:update_wish", args=[item.id]), {
            "title": "Aangepast", "url": "", "price": "", "repeatable": "",
        })
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("family:delete_post", args=[post.id]))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("family:update_person", args=[ContactPerson.objects.create(
            household=self.household,
            contact=Contact.objects.create(household=self.household, name="Persoon"),
            name="Ander lid",
        ).id]), {"name": "Ander lid", "birth_date": "", "email": "", "phone": ""})
        self.assertEqual(response.status_code, 403)

    def test_family_contacts_screen_renders_management_overlays(self):
        contact = Contact.objects.create(household=self.household, name="Familie De Vries")
        person = ContactPerson.objects.create(household=self.household, contact=contact, name="Piet de Vries")
        response = self.client.get(f"{reverse('family:index')}?tab=contacten")
        self.assertContains(response, f'contact-edit-{contact.id}')
        self.assertContains(response, f'person-edit-{person.id}')
