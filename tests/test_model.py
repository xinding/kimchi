#
# Project Burnet
#
# Copyright IBM, Corp. 2013
#
# Authors:
#  Adam Litke <agl@linux.vnet.ibm.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import unittest
import threading
import os
import time

import burnet.model
import burnet.objectstore
import utils

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp_store = '/tmp/burnet-store-test'

    def tearDown(self):
        os.unlink(self.tmp_store)

    def test_vm_info(self):
        inst = burnet.model.Model('test:///default', self.tmp_store)
        vms = inst.vms_get_list()
        self.assertEquals(1, len(vms))
        self.assertEquals('test', vms[0])

        keys = set(('state', 'cpu_stats', 'memory', 'screenshot', 'icon', 'vnc_port'))
        info = inst.vm_lookup('test')
        self.assertEquals(keys, set(info.keys()))
        self.assertEquals('running', info['state'])
        self.assertEquals(2048, info['memory'])
        self.assertEquals(None, info['icon'])

        self.assertRaises(burnet.model.NotFoundError,
                          inst.vm_lookup, 'nosuchvm')

    @unittest.skipUnless(utils.running_as_root(), 'Must be run as root')
    def test_vm_lifecycle(self):
        inst = burnet.model.Model(objstore_loc=self.tmp_store)

        with utils.RollbackContext() as rollback:
            params = {'name': 'test', 'disks': []}
            inst.templates_create(params)
            rollback.prependDefer(inst.template_delete, 'test')

            params = {'name': 'burnet-vm', 'template': '/templates/test'}
            inst.vms_create(params)
            rollback.prependDefer(inst.vm_delete, 'burnet-vm')

            vms = inst.vms_get_list()
            self.assertTrue('burnet-vm' in vms)

            inst.vm_start('burnet-vm')
            rollback.prependDefer(inst.vm_stop, 'burnet-vm')

            info = inst.vm_lookup('burnet-vm')
            self.assertEquals('running', info['state'])

        vms = inst.vms_get_list()
        self.assertFalse('burnet-vm' in vms)

    @unittest.skipUnless(utils.running_as_root(), 'Must be run as root')
    def test_vm_storage_provisioning(self):
        inst = burnet.model.Model(objstore_loc=self.tmp_store)

        with utils.RollbackContext() as rollback:
            params = {'name': 'test', 'disks': [{'size': 1}]}
            inst.templates_create(params)
            rollback.prependDefer(inst.template_delete, 'test')

            params = {'name': 'test-vm-1', 'template': '/templates/test'}
            inst.vms_create(params)
            rollback.prependDefer(inst.vm_delete, 'test-vm-1')

            disk_path = '/var/lib/libvirt/images/test-vm-1-0.img'
            self.assertTrue(os.access(disk_path, os.F_OK))
        self.assertFalse(os.access(disk_path, os.F_OK))

    @unittest.skipUnless(utils.running_as_root(), 'Must be run as root')
    def test_storagepool(self):
        inst = burnet.model.Model('qemu:///system', self.tmp_store)

        with utils.RollbackContext() as rollback:
            path = '/tmp/burnet-images'
            name = 'test-pool'
            if not os.path.exists(path):
                os.mkdir(path)

            pools = inst.storagepools_get_list()
            num = len(pools) + 1

            args = {'name': name,
                    'path': path,
                    'type': 'dir'}
            inst.storagepools_create(args)
            rollback.prependDefer(inst.storagepool_delete, name)

            pools = inst.storagepools_get_list()
            self.assertEquals(num, len(pools))

            poolinfo = inst.storagepool_lookup(name)
            self.assertEquals(path, poolinfo['path'])
            self.assertEquals('inactive', poolinfo['state'])

            inst.storagepool_activate(name)
            rollback.prependDefer(inst.storagepool_deactivate, name)

            poolinfo = inst.storagepool_lookup(name)
            self.assertEquals('active', poolinfo['state'])

        pools = inst.storagepools_get_list()
        self.assertEquals((num - 1), len(pools))

    @unittest.skipUnless(utils.running_as_root(), 'Must be run as root')
    def test_storagevolume(self):
        inst = burnet.model.Model('qemu:///system', self.tmp_store)

        with utils.RollbackContext() as rollback:
            path = '/tmp/burnet-images'
            pool = 'test-pool'
            vol = 'test-volume.img'
            if not os.path.exists(path):
                os.mkdir(path)

            args = {'name': pool,
                    'path': path,
                    'type': 'dir'}
            inst.storagepools_create(args)
            rollback.prependDefer(inst.storagepool_delete, pool)

            # Activate the pool before adding any volume
            inst.storagepool_activate(pool)
            rollback.prependDefer(inst.storagepool_deactivate, pool)

            vols = inst.storagevolumes_get_list(pool)
            num = len(vols) + 1
            params = {'name': vol,
                      'capacity': 1024,
                      'allocation': 512,
                      'format': 'raw'}
            inst.storagevolumes_create(pool, params)
            rollback.prependDefer(inst.storagevolume_delete, pool, vol)

            vols = inst.storagevolumes_get_list(pool)
            self.assertEquals(num, len(vols))

            inst.storagevolume_wipe(pool, vol)
            volinfo = inst.storagevolume_lookup(pool, vol)
            self.assertEquals(0, volinfo['allocation'])

            volinfo = inst.storagevolume_lookup(pool, vol)
            # Define the size = capacity + 16M
            size = volinfo['capacity'] + 16
            inst.storagevolume_resize(pool, vol, size)

            volinfo = inst.storagevolume_lookup(pool, vol)
            self.assertEquals(size, volinfo['capacity'])

    def test_multithreaded_connection(self):
        def worker():
            for i in xrange(100):
                ret = inst.vms_get_list()
                self.assertEquals('test', ret[0])

        inst = burnet.model.Model('test:///default', self.tmp_store)
        threads = []
        for i in xrange(100):
            t = threading.Thread(target=worker)
            t.setDaemon(True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def test_object_store(self):
        store = burnet.objectstore.ObjectStore(self.tmp_store)

        with store as session:
            # Test create
            session.store('foo', 'test1', {'a': 1})
            session.store('foo', 'test2', {'b': 2})

            # Test list
            items = session.get_list('foo')
            self.assertTrue('test1' in items)
            self.assertTrue('test2' in items)

            # Test get
            item = session.get('foo', 'test1')
            self.assertEquals(1, item['a'])

            # Test delete
            session.delete('foo', 'test2')
            self.assertEquals(1, len(session.get_list('foo')))

            # Test get non-existent item
            self.assertRaises(burnet.model.NotFoundError, session.get,
                              'a', 'b')

            # Test delete non-existent item
            self.assertRaises(burnet.model.NotFoundError, session.delete,
                              'foo', 'test2')

            # Test refresh existing item
            session.store('foo', 'test1', {'a': 2})
            item = session.get('foo', 'test1')
            self.assertEquals(2, item['a'])

    def test_object_store_threaded(self):
        def worker(ident):
            with store as session:
                session.store('foo', ident, {})

        store = burnet.objectstore.ObjectStore(self.tmp_store)

        threads = []
        for i in xrange(50):
            t = threading.Thread(target=worker, args=(i,))
            t.setDaemon(True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        with store as session:
            self.assertEquals(50, len(session.get_list('foo')))
            self.assertEquals(10, len(store._connections.keys()))

    def test_async_tasks(self):
        class task_except(Exception):
            pass
        def wait_task(model, taskid, timeout=5):
            for i in range(0, timeout):
                if model.task_lookup(taskid)['status'] == 'running':
                    time.sleep(1)

        def quick_op(cb, message):
            cb(message, True)

        def long_op(cb, params):
            time.sleep(params.get('delay', 3))
            cb(params.get('message', ''), params.get('result', False))

        def abnormal_op(cb, params):
            try:
                raise task_except
            except:
                cb("Exception raised", False)

        inst = burnet.model.Model('test:///default', objstore_loc=self.tmp_store)
        taskid = inst.add_task('', quick_op, 'Hello')
        wait_task(inst, taskid)
        self.assertEquals(1, taskid)
        self.assertEquals('finished', inst.task_lookup(taskid)['status'])
        self.assertEquals('Hello', inst.task_lookup(taskid)['message'])

        taskid = inst.add_task('', long_op,
                                     {'delay': 3, 'result': False,
                                      'message': 'It was not meant to be'})
        self.assertEquals(2, taskid)
        self.assertEquals('running', inst.task_lookup(taskid)['status'])
        self.assertEquals('OK', inst.task_lookup(taskid)['message'])
        wait_task(inst, taskid)
        self.assertEquals('failed', inst.task_lookup(taskid)['status'])
        self.assertEquals('It was not meant to be', inst.task_lookup(taskid)['message'])
        taskid = inst.add_task('', abnormal_op, {})
        wait_task(inst, taskid)
        self.assertEquals('Exception raised', inst.task_lookup(taskid)['message'])
        self.assertEquals('failed', inst.task_lookup(taskid)['status'])

    @unittest.skipUnless(utils.running_as_root(), 'Must be run as root')
    def test_delete_running_vm(self):
        inst = burnet.model.Model(objstore_loc=self.tmp_store)

        with utils.RollbackContext() as rollback:
            params = {'name': 'test', 'disks': []}
            inst.templates_create(params)
            rollback.prependDefer(inst.template_delete, 'test')

            params = {'name': 'burnet-vm', 'template': '/templates/test'}
            inst.vms_create(params)
            rollback.prependDefer(inst.vm_delete, 'burnet-vm')

            inst.vm_start('burnet-vm')
            rollback.prependDefer(inst.vm_stop, 'burnet-vm')

            inst.vm_delete('burnet-vm')

            vms = inst.vms_get_list()
            self.assertFalse('burnet-vm' in vms)

    def test_vm_list_sorted(self):
        inst = burnet.model.Model(objstore_loc=self.tmp_store)

        with utils.RollbackContext() as rollback:
            params = {'name': 'test', 'disks': []}
            inst.templates_create(params)
            rollback.prependDefer(inst.template_delete, 'test')

            params = {'name': 'burnet-vm', 'template': '/templates/test'}
            inst.vms_create(params)
            rollback.prependDefer(inst.vm_delete, 'burnet-vm')

            vms = inst.vms_get_list()

            self.assertEquals(vms, sorted(vms, key=unicode.lower))

    def test_use_test_host(self):
        inst = burnet.model.Model('test:///default', objstore_loc=self.tmp_store)

        with utils.RollbackContext() as rollback:
            params = {'name': 'test', 'disks': [],
                       'storagepool': '/storagepools/default-pool',
                       'domain': 'test',
                       'arch': 'i686'}

            inst.templates_create(params)
            rollback.prependDefer(inst.template_delete, 'test')

            params = {'name': 'burnet-vm', 'template': '/templates/test',}
            inst.vms_create(params)
            rollback.prependDefer(inst.vm_delete, 'burnet-vm')

            vms = inst.vms_get_list()

            self.assertTrue('burnet-vm' in vms)
