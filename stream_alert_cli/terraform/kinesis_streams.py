"""
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""


def generate_kinesis_streams(cluster_name, cluster_dict, config):
    """Add the Kinesis Streams module to the Terraform cluster dict.

    Args:
        cluster_name (str): The name of the currently generating cluster
        cluster_dict (defaultdict): The dict containing all Terraform config for
                                    a given cluster.
        config (dict): The loaded config from the 'conf/' directory

    Returns:
        bool: Result of applying the kinesis module
    """
    prefix = config['global']['account']['prefix']
    kinesis_module = config['clusters'][cluster_name]['modules']['kinesis']['streams']
    shard_level_metrics = kinesis_module.get('shard_level_metrics', [])

    cluster_dict['module']['kinesis_{}'.format(cluster_name)] = {
        'source': 'modules/tf_stream_alert_kinesis_streams',
        'account_id': config['global']['account']['aws_account_id'],
        'region': config['clusters'][cluster_name]['region'],
        'cluster_name': cluster_name,
        'prefix': config['global']['account']['prefix'],
        'stream_name': '{}_{}_stream_alert_kinesis'.format(prefix, cluster_name),
        'shard_level_metrics': shard_level_metrics,
        'shards': kinesis_module['shards'],
        'retention': kinesis_module['retention'],
        'create_user': kinesis_module.get('create_user', True),
        'trusted_accounts': kinesis_module.get('trusted_accounts', [])
    }

    return True
