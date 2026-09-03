from unittest import TestCase, mock

from etesync_dav.local_cache import Collection, Etebase


class CollectionCacheTest(TestCase):
    @mock.patch("etesync_dav.local_cache.db.database_proxy")
    def test_collection_metadata_is_marked_dirty(self, _database_proxy):
        cache_collection = mock.Mock(eb_col=b"cached")
        remote_collection = mock.Mock(meta={"name": "Old"})
        collection_manager = mock.Mock()
        collection_manager.cache_load.return_value = remote_collection
        collection_manager.cache_save.return_value = b"updated"

        collection = Collection(collection_manager, cache_collection)
        collection.update_meta({"name": "New"})

        self.assertEqual(remote_collection.meta["name"], "New")
        self.assertEqual(cache_collection.eb_col, b"updated")
        self.assertTrue(cache_collection.dirty)
        cache_collection.save.assert_called_once_with()

    @mock.patch("etesync_dav.local_cache.db.database_proxy")
    def test_collection_delete_is_queued(self, _database_proxy):
        cache_collection = mock.Mock(eb_col=b"cached", deleted=False, dirty=False)
        collection_manager = mock.Mock()

        Collection(collection_manager, cache_collection).delete()

        self.assertTrue(cache_collection.deleted)
        self.assertTrue(cache_collection.dirty)
        cache_collection.save.assert_called_once_with()

    @mock.patch("etesync_dav.local_cache.db.database_proxy")
    def test_changed_collection_is_uploaded_and_recached(self, _database_proxy):
        cache_collection = mock.Mock(eb_col=b"cached", deleted=True, dirty=True, new=True, stoken=None)
        remote_collection = mock.Mock(stoken="new-token")
        collection_manager = mock.Mock()
        collection_manager.cache_load.return_value = remote_collection
        collection_manager.cache_save.return_value = b"recached"

        etebase = Etebase.__new__(Etebase)
        etebase.user = mock.Mock()
        etebase.user.collections.where.return_value = [cache_collection]
        etebase.etebase = mock.Mock()
        etebase.etebase.get_collection_manager.return_value = collection_manager

        etebase.push_collection_list()

        collection_manager.cache_load.assert_called_once_with(b"cached")
        remote_collection.delete.assert_called_once_with()
        collection_manager.upload.assert_called_once_with(remote_collection, None)
        self.assertEqual(cache_collection.eb_col, b"recached")
        self.assertEqual(cache_collection.stoken, "new-token")
        self.assertFalse(cache_collection.dirty)
        self.assertFalse(cache_collection.new)
