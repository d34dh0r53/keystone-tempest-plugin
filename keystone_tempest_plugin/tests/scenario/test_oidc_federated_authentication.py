# Copyright 2022 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import uuid

from keystoneauth1 import identity
from keystoneauth1 import session as ks_session
from tempest import config
from tempest.lib.common.utils import data_utils
import testtools

from .keycloak import KeycloakClient
from keystone_tempest_plugin.tests import base

CONF = config.CONF

class TestOidcFederatedAuthentication(base.BaseIdentityTest):

    def _setup_settings(self):
        # Keycloak Settings
        self.idp_id = CONF.fed_scenario.idp_id
        self.idp_remote_ids = CONF.fed_scenario.idp_remote_ids
        self.idp_url = CONF.fed_scenario.idp_oidc_url
        self.idp_client_id = CONF.fed_scenario.idp_client_id
        self.idp_client_secret = CONF.fed_scenario.idp_client_secret
        self.idp_password = CONF.fed_scenario.idp_password
        self.idp_username = CONF.fed_scenario.idp_username

        self.protocol_id = CONF.fed_scenario.protocol_id
        self.keystone_v3_endpoint = CONF.identity.uri_v3

        # mapping settings
        self.mapping_remote_type = CONF.fed_scenario.mapping_remote_type
        self.mapping_user_name = CONF.fed_scenario.mapping_user_name
        self.mapping_group_name = CONF.fed_scenario.mapping_group_name
        self.mapping_group_domain_name = \
            CONF.fed_scenario.mapping_group_domain_name

    def _setup_mapping(self):
        self.mapping_id = data_utils.rand_uuid_hex()
        rules = [{
            'local': [
                {
                    'user': {'name': self.mapping_user_name}
                },
                {
                    'group': {
                        'domain': {'name': self.mapping_group_domain_name},
                        'name': self.mapping_group_name
                    }
                }
            ],
            'remote': [
                {
                    'type': self.mapping_remote_type
                }
            ]
        }]
        mapping_ref = {'rules': rules}
        self.mappings_client.create_mapping_rule(self.mapping_id, mapping_ref)
        self.addCleanup(
            self.mappings_client.delete_mapping_rule, self.mapping_id)

    def _setup_protocol(self):
        self.idps_client.add_protocol_and_mapping(
            self.idp_id, self.protocol_id, self.mapping_id)
        self.addCleanup(
            self.idps_client.delete_protocol_and_mapping,
            self.idp_id,
            self.protocol_id)

    def setUp(self):
        super(TestOidcFederatedAuthentication, self).setUp()
        self._setup_settings()

        # Setup mapping and protocol
        self._setup_mapping()
        self._setup_protocol()
        self.keycloak = KeycloakClient(
            keycloak_url=self.idp_url,
            keycloak_username=self.idp_username,
            keycloak_password=self.idp_password,
        )

    def _setup_user(self, email=None):
        email = email if email else f'test-{uuid.uuid4().hex}@example.com'
        self.keycloak.create_user(email, 'Test', 'User')
        return email

    def _request_unscoped_token(self, user):
        auth = identity.v3.OidcPassword(
            auth_url=self.keystone_v3_endpoint,
            identity_provider=self.idp_id,
            protocol=self.protocol_id,
            client_id=self.idp_client_id,
            client_secret=self.idp_client_secret,
            access_token_endpoint=self.keycloak.token_endpoint,
            discovery_endpoint=self.keycloak.discovery_endpoint,
            username=user,
            password='secret'
        )
        s = ks_session.Session(auth)
        return s.get_auth_headers()

    def _test_request_unscoped_token(self):
        user = self._setup_user()
        token = self._request_unscoped_token(user)
        self.assertNotEmpty(token)

    def _test_request_scoped_token(self):
        user = self._setup_user()
        token = self._request_unscoped_token(user)
        token_id = token['X-Auth-Token']

        projects = self.auth_client.get_available_projects_scopes(
            self.keystone_v3_endpoint, token_id)['projects']
        self.assertNotEmpty(projects)

        # Get a scoped token to one of the listed projects
        self.tokens_client.auth(
            project_id=projects[0]['id'], token=token_id)


class TestOidcFederatedExternalAuthentication(
    TestOidcFederatedAuthentication):

    @testtools.skipUnless(CONF.identity_feature_enabled.federation,
                          "Federated Identity feature not enabled")
    @testtools.skipUnless(CONF.identity_feature_enabled.external_idp,
                          "External identity provider is not available")
    @testtools.skipUnless(CONF.fed_scenario.protocol_id == 'openid',
                          "Protocol not openid")
    def test_request_unscoped_token(self):
        self._test_request_unscoped_token()

    @testtools.skipUnless(CONF.identity_feature_enabled.federation,
                          "Federated Identity feature not enabled")
    @testtools.skipUnless(CONF.identity_feature_enabled.external_idp,
                          "External identity provider is not available")
    @testtools.skipUnless(CONF.fed_scenario.protocol_id == 'openid',
                          "Protocol not openid")
    def test_request_scoped_token(self):
        self._test_request_scoped_token()
