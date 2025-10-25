#!/usr/bin/python
# -*- coding: utf-8 -*-
DOCUMENTATION = r'''
module: custom.bankx.sandbox
description: provision development sandboxes via the internal sanbox api
parameters:
  api-endpoint: 
    type: string
    description: the host + port of the API server
  api-token: 
    type: string
    description: bearer token for the API server 
'''

from ansible.module_utils.basic import AnsibleModule
import re
import requests
from uuid import uuid4
from ansible.module_utils.urls import fetch_url

class APIClient():
    def __init__(self, module):
        self.module = module
        self.base_url = module.params['api_endpoint']
        self.token = module.params['api_token']
    
    def make_request(self, uri_path, method, data=None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "If-Match": self.module.params.get("resource_version", "")
        }

        data = dict(
            name = self.module.params['name'],
            owner_email = self.module.params['owner_email'],
            size = self.module.params["size"],
            ttl_days = self.module.params["ttl_days"],
            allowed_cidrs = self.module.params["allowed_cidrs"],
            id = str(uuid4())
        )    

        url = self.base_url + ('' if uri_path.startswith('/') else '/') + uri_path
        try:
            if method == "PATCH":
                response = requests.patch(url, json=data, headers=headers)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers)
            elif method == "DELETE":
                response = requests.delete(url, json=data, headers=headers)
            elif method == "GET":
                response = requests.get(url, json=data, headers=headers)
        except Exception as e:
            self.module.fail_json(
                msg=str(e)
            )

        if response.status_code and response.status_code >= 400:
            self.module.fail_json(msg="API failure", **response.json())

        return response.json(), response.status_code

def main():
    module_args = dict(
        api_endpoint = dict(type=str, required=True),
        api_token = dict(type=str, required=True),
        name = dict(type=str, required=True), 
        owner_email = dict(type=str, required=True),
        size = dict(type=str, required=True),
        ttl_days = dict(type=int, required=True),
        allowed_cidrs = dict(type=list[str], required=True),
        resource_version = dict(type=str, required=False),
        state = dict(type=str, required=True, choices=['present', 'absent']),
        sandbox_id = dict(type=str, required=False)
    )
    
    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=False
    )

    client = APIClient(module)

    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    if module.params.get("state") == "present":
        _id = module.params.get("sandbox_id", "")
        if _id:
            response, code = client.make_request(f"/v1/sandboxes/{_id}", "PATCH")
        else:
            response, code = client.make_request("/v1/sandboxes", "POST")
        if code == 200:
            result["msg"] = "Sandbox configuration already up-to-date"
            result["original_message"] = response
            module.exit_json(**result)
        elif code == 202:
            _id = response.get("sandbox_id")
            ops, code = client.make_request(f"/v1/operations/{_id}", "GET")
            result["changed"] = True
            result["original_message"] = response
            result["msg"] = ops
            module.exit_json(**result)

    if module.params.get("state") == "absent":
        _id = module.params.get("sandbox_id", "")
        response, code = client.make_request(f"/v1/sandboxes/{_id}", "DELETE")
        if code == 200:
            result["msg"] = "Sandbox already deleted"
            result["original_message"] = response
            module.exit_json(**result)
        elif code == 202:
            result["changed"] = True
            result["original_message"] = response
            result["msg"] = f"sandbox deleted"
            module.exit_json(**result)
        
def validate_input(module):
    email = module.params["email"]
    valid_email = re.compile("^[a-zA-Z0-9._-]+@[a-zA-Z0-9_.-]+.[a-z]{2,3}$")
    valid_cidr = re.compile("^[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}/[0-9]{1,2}$")
    if not valid_email.match(email):
        module.fail_json(
            msg="Provided email does not match regular expression ^[a-zA-Z0-9._-]+@[a-zA-Z0-9_.-]+.[a-z]{2,3}$"
        )
    if not 0 < module.params['ttl_days'] <= 30:
        module.fail_json(
            msg="ttl_days must be between 1 and 30"
        )
    for cidr in module.params['allowed_cidrs']:
        if not valid_cidr.match(cidr):
            module.fail_json(
                msg=f"invalid cidr range in allowed_cidrs: {cidr}"
            )

if __name__ == '__main__':
    main()
