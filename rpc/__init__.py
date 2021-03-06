#!/usr/bin/python
# -*- coding: utf-8 -*-
# # Copyright (c) 2017-2019, The Sumokoin Project (www.sumokoin.org)
'''
RPC requests
'''

from __future__ import print_function

import sys
import requests, json
from requests.exceptions import ConnectionError

from uuid import uuid4

from Queue import Queue
from threading import Thread
from multiprocessing import Event
from time import sleep

from requests.auth import HTTPDigestAuth

rpc_id = 0

wallet_rpc_errors = {
                     "WALLET_RPC_ERROR_CODE_UNKNOWN_ERROR": "Unknown error",
                    "WALLET_RPC_ERROR_CODE_WRONG_ADDRESS": "Invalid address format",
                    "WALLET_RPC_ERROR_CODE_DAEMON_IS_BUSY": "Daemon is busy",
                    "WALLET_RPC_ERROR_CODE_GENERIC_TRANSFER_ERROR": "Unknown transfer error",
                    "WALLET_RPC_ERROR_CODE_WRONG_PAYMENT_ID": "Invalid payment ID format",
                    "WALLET_RPC_ERROR_CODE_TRANSFER_TYPE": "Wrong transfer type",
                    "WALLET_RPC_ERROR_CODE_DENIED": "Transaction was denied",
                    "WALLET_RPC_ERROR_CODE_WRONG_TXID": "Wrong transaction ID",
                    "WALLET_RPC_ERROR_CODE_WRONG_SIGNATURE": "Wrong signature",
                    "WALLET_RPC_ERROR_CODE_WRONG_KEY_IMAGE": "Wrong key image",
                    "WALLET_RPC_ERROR_CODE_WRONG_URI": "Wrong URI",
                    "WALLET_RPC_ERROR_CODE_WRONG_INDEX": "Wrong index",
                    "WALLET_RPC_ERROR_CODE_NOT_OPEN": "Wallet not open",
}

class RPCRequest(Thread):
    headers = {'content-type': 'application/json; charset=UTF-8'}

    def __init__(self, rpc_input, url, app, rpc_user_name = None, rpc_password=None):
        Thread.__init__(self)
        self.url = url
        self.rpc_input = rpc_input
        self.app = app
        self.auth = None

        if rpc_user_name is not None and rpc_password is not None:
            self.auth=HTTPDigestAuth(rpc_user_name, rpc_password)

        self.response_queue = Queue(1)
        self.daemon = True


    def run(self):
        res = self._send_request()
        self.response_queue.put(res)


    def stop(self):
        self.is_stopped = True


    def _send_request(self):
        global rpc_id
        rpc_id += 1
        self.rpc_input.update({"jsonrpc": "2.0", "id": "%d" % rpc_id})

        try:
            if self.auth is not None:
                response = requests.post(
                    self.url,
                    data=json.dumps(self.rpc_input),
                    headers=self.headers,
                    auth=self.auth)
            else:
                response = requests.post(
                    self.url,
                    data=json.dumps(self.rpc_input),
                    headers=self.headers)

            res_json = response.json()
        except ConnectionError:
            return {"status": "Disconnected" }
        except:
            return {"status": "Unknown error" }
        else:
            if 'result' in res_json:
                if not 'status' in res_json['result']:
                    res_json['result']['status'] = "OK"
                return res_json['result']
            elif 'error' in res_json:
                # print(json.dumps(res_json, indent=4), file=sys.stderr)
                res_json['error']['status'] = "ERROR"
                for k, v in wallet_rpc_errors.iteritems():
                    if k in res_json['error']['message']:
                        res_json['error']['message'] = res_json['error']['message'].replace(k, v)
                        break
                return res_json['error']

        # print(json.dumps(res_json, indent=4))
        return res_json


    def get_result(self):
        while self.response_queue.empty():
            self.app.processEvents()
        return self.response_queue.get()



class DaemonRPCRequest():
    def __init__(self, app):
        self.port = 19734
        self.url = "http://localhost:%d/json_rpc" % self.port
        self.app = app

    def send_request(self, rpc_input):
        req = RPCRequest(rpc_input, self.url, self.app)
        req.start()
        return req.get_result()

    def get_info(self):
        rpc_input = {"method": "get_info"}
        return self.send_request(rpc_input)


class WalletRPCRequest():
    def __init__(self, app, rpc_user_name, rpc_password):
        self.port = 19738
        self.url = "http://localhost:%d/json_rpc" % self.port
        self.app = app
        self.rpc_user_name = rpc_user_name
        self.rpc_password = rpc_password

    def send_request(self, rpc_input, no_wait=False):
        req = RPCRequest(rpc_input, self.url, self.app, self.rpc_user_name, self.rpc_password)
        req.start()
        if no_wait: return None
        return req.get_result()

    def query_key(self, key_type, passphrase=""):
        rpc_input = {"method":"query_key",
                     "params": {"key_type": key_type,
                                "passphrase": passphrase}
                    }
        res = self.send_request(rpc_input)
        if res['status'] == 'OK':
            return res['key']
        elif res['status'] == 'ERROR':
            return res['message']
        else:
            return ""

    def get_address(self, account_index = 0):
        params = {"account_index": account_index}
        rpc_input = {"method": "getaddress",
                     "params": params}
        return self.send_request(rpc_input)

    def create_address(self):
        rpc_input = {"method":"create_address"}
        res = self.send_request(rpc_input)
        if res['status'] == 'OK':
            return res
        return res['status']

    def get_balance(self):
        rpc_input = {"method":"getbalance"}
        res = self.send_request(rpc_input)
        if res['status'] == 'OK':
            per_subaddress = []
            if 'per_subaddress' in res:
                per_subaddress = res['per_subaddress']
            return (res['balance'], res['unlocked_balance'], per_subaddress)
        return (0, 0, [])

    def get_transfers(self, filter_by_height=False, min_height=0, max_height=0, tx_in=True, tx_out=True, tx_pending=False, tx_in_pool=False):
        rpc_input = {"method":"get_transfers"}
        params = {}
        if filter_by_height:
            params['filter_by_height'] = True
            params['min_height'] = min_height
            params['max_height'] = max_height if max_height > 0 else 0x7fffffff
        params["in"] = tx_in
        params["out"] = tx_out
        params["pending"] = tx_pending
        params["pool"] = tx_in_pool
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def rescan_spent(self):
        rpc_input = {"method": "rescan_spent"}
        return self.send_request(rpc_input)

    def rescan_bc(self):
        rpc_input = {"method": "rescan_blockchain"}
        return self.send_request(rpc_input)

    def transfer_split(self, amount, address, payment_id, priority, mixin):
        rpc_input = {"method": "transfer_split"}
        params = {"destinations": [{"amount" : amount, "address": address}],
                  "priority": priority,
                  "mixin": mixin}
        if payment_id:
            params["payment_id"] = payment_id

        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def transfer_all(self, address, payment_id, priority, mixin, account_index=0, subaddr_indices=[0]):
        rpc_input = {"method": "sweep_all"}
        params = {
            "address": address,
            "account_index": account_index,
            "subaddr_indices": subaddr_indices,
            "priority": priority,
            "mixin": mixin
        }
        if payment_id:
            params["payment_id"] = payment_id

        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def set_tx_notes(self, txids, notes):
        rpc_input = {"method": "set_tx_notes"}
        params = {"txids": txids, "notes": notes}
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def make_integrated_address(self, payment_id):
        rpc_input = {"method": "make_integrated_address"}
        params = {"payment_id": payment_id}
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def get_address_book(self):
        rpc_input = {"method": "get_address_book"}
        return self.send_request(rpc_input)

    def add_address_book(self, address, payment_id, desc):
        rpc_input = {"method": "add_address_book"}
        params = {"address": address}
        if payment_id:
            params["payment_id"] = payment_id
        if desc:
            params["description"] = desc
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def delete_address_book(self, index):
        rpc_input = {"method": "delete_address_book"}
        params = {"index": index}
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def stop_wallet(self, no_wait=False):
        rpc_input = {"method":"stop_wallet"}
        return self.send_request(rpc_input, no_wait)

    def save_wallet_to_file(self):
        rpc_input = {"method":"store"}
        return self.send_request(rpc_input)

    def restore_deterministic_wallet(self, seed, restore_height, filename,
                                    seed_offset_passphrase, password, language):
        rpc_input = {"method":"restore_deterministic_wallet"}
        params = {"seed": seed,
                  "restore_height": restore_height,
                  "filename": filename,
                  "seed_offset": seed_offset_passphrase,
                  "password": password,
                  "language": language,
                }
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def create_wallet(self, filename, password, language):
        rpc_input = {"method":"create_wallet"}
        params = {"filename": filename,
                  "password": password,
                  "language": language,
                }
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def set_wallet_seed_language(self, language):
        rpc_input = {"method":"set_seed_language"}
        params = {"language": language,
                }
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def open_wallet(self, filename, password):
        rpc_input = {"method":"open_wallet"}
        params = {"filename": filename,
                  "password": password
                }
        rpc_input["params"] = params
        return self.send_request(rpc_input)

    def close_wallet(self, no_wait=False):
        rpc_input = {"method":"close_wallet"}
        return self.send_request(rpc_input, no_wait)

    def get_version(self):
        rpc_input = {"method":"get_version"}
        return self.send_request(rpc_input)

    def change_wallet_password(self, old_password, new_password):
        rpc_input = {"method":"change_wallet_password"}
        params = {"old_password": old_password,
                  "new_password": new_password}
        rpc_input["params"] = params
        return self.send_request(rpc_input)
