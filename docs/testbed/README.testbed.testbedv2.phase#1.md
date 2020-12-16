# testbed v2 design
* goal: support running multiple DUTs testbed with inter-DUT connection(Spytest).
* features:
    * support dynamically vlan assignment upon `add_topo`.
    * support link state propagation for inter-DUTs connections.
* components:
    * test users
    * a Redis db
    * servercfgd
        * running on the same server of the database.
        * responsible for the db provisioning and interaction with test users.
    * labcfgd
        * running over root/leaf fanout switchs
        * subscribe to key changes of the database and act accordingly.
* design principle:
    * a core `Redis` database hosting all connections' metadata.
    * based on the pub/sub architecture, once test user modifies certain keys in db, `labcfgd` will respond to key changes and modify connection/port state.
        * dynamic vlan modification to database will cause `labcfgd` assign the vlan to the corresponding port on fanout.
        * virtual link status change to database will cause `labcfgd` to open/shutdown the physical port connecting to DUT.
* stages:
    * phase#1: initial db setup and provision.
    * phase#2: dynamic vlan assignment support.
    * phase#3: link state propagation support.

## connection db schema
* requirements:
  * dataset in file:
    * `sonic_<lab_name>_devices.csv`
    * `sonic_<lab_name>_links.csv`
* connection db schema:
  * `LAB_CONNECTION_GRAPH_VERSIONS`:
    * zset of md5sum values of connection graph files used to provision the database
      * scores are the timestamps when md5sum values are added, to ensure they are chronological
      * with the last one in zset are the current-in-use connection graph md5sum value and its added timestamp
    * users that wish to provision the db will check to see if the md5sum value of connection graph file is in `LAB_CONNECTION_GRAPH_VERSIONS`
      * if `yes`, stop provision
        * prevent users with dated connection graph file try to provision the db.
      * if `no`, try to provision and add the md5sum value to `LAB_CONNECTION_GRAPH_VERSIONS` with current time as score.
        * it will also trim `LAB_CONNECTION_GRAPH_VERSIONS` to keep most-recent 20 md5sum values.
  * `LAB_META`
    * `ServerState`:
      * `active`
      * `provisioning`
      * `down`
  * `SWITCH_TABLE:switch_name`
    * `HwSku`
    * `ManagementIp`
    * `Type`
      * `leaf_fanout`
      * `root_fanout`
  * `DUT_TABLE:dut_name`
    * `HwSku`
    * `ManagementIp`
    * `ProvisionStatus`
      * `not provisioned`
      * `in progress`
      * `provisioned/unique id`
  * `SERVER_TABLE:server_name`
    * `HwSku`
    * `ManagementIp`
  * `PORT_LIST:<switch_name|dut_name|server_name>`
    * set storing all the ports of a device
  * `PORT_TABLE:switch_name:port_name`
    * `BandWidth`
    * `VlanType`
      * `access`
      * `trunk`
    * `PhyPeerPort`
      * physical peer port, FK to `PORT_TABLE`
  * `VLAN_LIST:switch_name:port_name`:
    * set contains all vlan ids assigned to port.
  * `VLANIDPOOL_SET`:
    * set of unique available vlan ids
  * `VIRTLINKS_TABLE:endport0:endport1`: `endport` is FK to `PORT_TABLE`
    * `Status`
      * `active`
      * `inactive`

## phase one
* in phase one, we only cover the connection db setup and provision.
* Ansible variables added:
  * `add_topo`:
    * `enable_connection_db`: enable setup and provision connection db
    * `connection_db_host`: specifies which server to host connection db and `servercfgd`
    * `connection_db_mapping`: we store the data from different connection graph files in different databases.
      * like `{'str': 0, 'str2': 1}`
    * `enfornce_provision_server_daemon`: enforce install server daemon even there is one running.
  * `remove_topo`:
    * `disable_connection_db`:
* db config:
  * enable snapshot
  * enable `AOF`
  * binds to `0.0.0.0`
  * disable authentication
  * enable all keyspace events

### db setup
* Ansible role `connection_db`
  * called in `add_topo` with `action: start_db` if `enable_connection_db` is `True`
    * ensure Redis and py-redis is installed.
      * if Redis is newly-installed
        * initialize each db based on `connection_db_mapping`
        * init `server_state` to `down`
    * ensure servercfgd is running.
      * if `enforce_provision_server_daemon` is `True`, enforce re-deploy server daemon
  * called in `remove_topo` with `action: stop_db` if `disable_connection_db` is `True`
    * ensure servercfgd is stopped
    * ensure Redis and py-redis is removed 


### db provision
* ansible library `provision_connection_db`:
  * called in `add_topo`
  * parse devices and connection links
  * calls `provision_connection_db` rpc call.
* what db server `provision_connection_db` does?
  1. acquire db provision lock
     * if wait timeout, raises an error to abort `add_topo`
  2. check md5sum is in `LAB_CONNECTION_GRAPH_VERSIONS`
     * if `yes`, releas lock and returns.
     * if `no`, add md5sum value to `LAB_CONNECTION_GRAPH_VERSION` with current timestamp as score.
       * trim `LAB_CONNECTION_GRAPH_VERSION` to ensure most-recent 20 entries
  3. change `server_state` to `provisioning`
  4. remove all keys in db
  5. add_device
  6. add_phy_connection
  7. change `server_state` to `active`
  8. release lock and returns

### connection_graph_facts
* add an extra parameters `conn_graph_facts_src`, could be either `from_db` or `from_file`
  * if `from_db`, retrieve those data from connection db
    * should ensure `server_state` is active
  * if `from_file`, fall back to parse connection graph file.

### some extreme scenarios
1. what if there is power outage for server?
  * Redis is configured with both snapshot and AOF persistence
  * might have db cluster in the future
2. what if the user forcely stops db provision in `add_topo`(`Ctr + C`), will this leave db in inconsistent state?
  * no, since servercfgd is a rpc server, even the client stops, the call to provision the db will finish eventually.
  * so be careful in provisioning the db, maybe tryout with `conn_graph_facts_src=from_file` first to test out connection changes.

## phase 2
### topology description
```
topology:
  host_interfaces:
    - "0.0"
    - "0.1"
    - "0.2"
    - "0.3"
    - "1.0"
    - "1.1"
    - "1.2"
    - "1.3"
    - "2.0"
    - "2.1"
    - "2.2"
    - "2.3"
    - "3.0"
    - "3.1"
    - "3.2"
    - "3.3"
  peer_interfaces:
    - 0.4,1.8
    - 0.5,1.9
    - 0.6,1.10
    - 0.7,1.11
    - 0.8,3.4
    - 0.9,3.5
    - 0.10,3.6
    - 0.11,3.7
    - 0.12,2.12
    - 0.13,2.13
    - 0.14,2.14
    - 0.15,2.15
    - 1.4,2.8
    - 1.5,2.9
    - 1.6,2.10
    - 1.7,2.11
    - 1.12,3.12
    - 1.13,3.13
    - 1.14,3.14
    - 1.15,3.15
    - 2.4,3.8
    - 2.5,3.9
    - 2.6,3.10
    - 2.7,3.11
```

## questions


## references
* https://www.ansibletutorials.com/installing-redis  
* https://docs.ansible.com/ansible/latest/user_guide/playbooks_reuse_roles.html  
* 
