from types import SimpleNamespace
from unittest import TestCase

import etesync as api
import peewee as pw

from etesync_dav.local_cache import db, models
from etesync_dav.radicale.href_mapper import HrefMapper as LegacyHrefMapper
from etesync_dav.radicale.storage import Collection as LegacyCollection
from etesync_dav.radicale.storage_etebase_collection import Collection as EtebaseCollection


class HrefMappingTest(TestCase):
    def test_etebase_href_lookup_is_scoped_to_collection(self):
        database = pw.SqliteDatabase(":memory:", pragmas={"foreign_keys": 1})
        db.database_proxy.initialize(database)
        database.create_tables([models.User, models.CollectionEntity, models.ItemEntity, models.HrefMapper])
        alice = models.User.create(username="alice")
        bob = models.User.create(username="bob")
        alice_collection = models.CollectionEntity.create(local_user=alice, uid="alice-col", eb_col=b"alice")
        bob_collection = models.CollectionEntity.create(local_user=bob, uid="bob-col", eb_col=b"bob")
        alice_item = models.ItemEntity.create(collection=alice_collection, uid="alice-item", eb_item=b"alice")
        bob_item = models.ItemEntity.create(collection=bob_collection, uid="bob-item", eb_item=b"bob")
        models.HrefMapper.create(content=alice_item, href="shared.ics")
        models.HrefMapper.create(content=bob_item, href="shared.ics")
        collection = EtebaseCollection.__new__(EtebaseCollection)
        collection.collection = SimpleNamespace(cache_col=bob_collection)

        href_mapper = collection._get_href_mapper("shared.ics")

        self.assertEqual(href_mapper.content, bob_item)
        database.close()

    def test_legacy_href_lookup_is_scoped_to_journal(self):
        database = pw.SqliteDatabase(":memory:", pragmas={"foreign_keys": 1})
        api.db.database_proxy.initialize(database)
        database.create_tables([api.cache.User, api.cache.JournalEntity, api.pim.Content, LegacyHrefMapper])
        alice = api.cache.User.create(username="alice")
        bob = api.cache.User.create(username="bob")
        alice_journal = api.cache.JournalEntity.create(local_user=alice, version=1, uid="alice-journal", content=b"{}")
        bob_journal = api.cache.JournalEntity.create(local_user=bob, version=1, uid="bob-journal", content=b"{}")
        alice_content = api.pim.Content.create(journal=alice_journal, uid="alice-item", content="alice")
        bob_content = api.pim.Content.create(journal=bob_journal, uid="bob-item", content="bob")
        LegacyHrefMapper.create(content=alice_content, href="shared.ics")
        LegacyHrefMapper.create(content=bob_content, href="shared.ics")
        collection = LegacyCollection.__new__(LegacyCollection)
        collection.journal = SimpleNamespace(_cache_obj=bob_journal)

        href_mapper = collection._get_href_mapper("shared.ics")

        self.assertEqual(href_mapper.content, bob_content)
        database.close()
