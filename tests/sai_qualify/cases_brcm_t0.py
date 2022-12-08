"""
Test cases list under test/sai_test
"""
TEST_CASE = [
        "sai_sanity_test.SaiSanityTest",
        "sai_vlan_test.Vlan_Domain_Forwarding_Test",
        "sai_vlan_test.UntagAccessToAccessTest",
        "sai_vlan_test.MismatchDropTest",
        "sai_vlan_test.TaggedFrameFilteringTest",
        "sai_vlan_test.UnTaggedFrameFilteringTest",
        "sai_vlan_test.TaggedVlanFloodingTest",
        "sai_vlan_test.UnTaggedVlanFloodingTest",
        "sai_vlan_test.BroadcastTest",
        "sai_vlan_test.UntaggedMacLearningTest",
        "sai_vlan_test.TaggedMacLearningTest",
        "sai_vlan_test.VlanMemberListTest",
        "sai_vlan_test.VlanMemberInvalidTest",
        "sai_vlan_test.DisableMacLearningTaggedTest",
        "sai_vlan_test.DisableMacLearningUntaggedTest",
        "sai_vlan_test.ArpRequestFloodingTest",
        "sai_vlan_test.ArpRequestLearningTest",
        "sai_vlan_test.TaggedVlanStatusTest",
        "sai_vlan_test.UntaggedVlanStatusTest",
        "sai_fdb_test.L2PortForwardingTest",
        "sai_fdb_test.VlanLearnDisableTest",
        "sai_fdb_test.BridgePortLearnDisableTest",
        "sai_fdb_test.NonBridgePortNoLearnTest",
        "sai_fdb_test.NewVlanmemberLearnTest",
        "sai_fdb_test.RemoveVlanmemberLearnTest",
        "sai_fdb_test.InvalidateVlanmemberNoLearnTest",
        "sai_fdb_test.BroadcastNoLearnTest",
        "sai_fdb_test.MulticastNoLearnTest",
        "sai_fdb_test.FdbAgingTest",
        "sai_fdb_test.FdbAgingAfterMoveTest",
        "sai_fdb_test.FdbMacMovingAfterAgingTest",
        "sai_fdb_test.FdbFlushVlanStaticTest",
        "sai_fdb_test.FdbFlushPortStaticTest",
        "sai_fdb_test.FdbFlushAllStaticTest",
        "sai_fdb_test.FdbFlushVlanDynamicTest",
        "sai_fdb_test.FdbFlushPortDynamicTest",
        "sai_fdb_test.FdbFlushAllDynamicTest",
        "sai_fdb_test.FdbFlushAllTest",
        "sai_fdb_test.FdbDisableMacMoveDropTest",
        "sai_fdb_test.FdbDynamicMacMoveTest",
        "sai_fdb_test.FdbStaticMacMoveTest",
        "sai_lag_test.LagConfigTest",
        "sai_lag_test.LoadbalanceOnSrcPortTest",
        "sai_lag_test.LoadbalanceOnDesPortTest",
        "sai_lag_test.LoadbalanceOnSrcIPTest",
        "sai_lag_test.LoadbalanceOnDesIPTest",
        "sai_lag_test.LoadbalanceOnProtocolTest",
        "sai_lag_test.DisableEgressTest",
        "sai_lag_test.DisableIngressTest",
        "sai_lag_test.RemoveLagMemberTest",
        "sai_lag_test.AddLagMemberTest",
        "sai_lag_test.IndifferenceIngressPortTest",
        "sai_neighbor_test.NoHostRouteTest",
        "sai_neighbor_test.NoHostRouteTestV6",
        "sai_neighbor_test.AddHostRouteTest",
        "sai_neighbor_test.AddHostRouteTestV6",
        "sai_neighbor_test.RemoveAddNeighborTestIPV4",
        "sai_neighbor_test.RemoveAddNeighborTestIPV6",
        "sai_neighbor_test.NhopDiffPrefixRemoveLonger",
        "sai_neighbor_test.NhopDiffPrefixRemoveLongerV6",
        "sai_neighbor_test.NhopDiffPrefixRemoveShorter",
        "sai_neighbor_test.NhopDiffPrefixRemoveShorterV6",
        "sai_rif_test.IngressMacUpdateTest",
        "sai_rif_test.IngressMacUpdateTestV6",
        "sai_rif_test.IngressDisableTestV4",
        "sai_rif_test.IngressDisableTestV6",
        "sai_rif_test.IngressMtuTestV4",
        "sai_rif_test.IngressMtuTestV6",
        "sai_route_test.RouteRifTest",
        "sai_route_test.RouteRifv6Test",
        "sai_route_test.LagMultipleRouteTest",
        "sai_route_test.LagMultipleRoutev6Test",
        "sai_route_test.DropRouteTest",
        "sai_route_test.DropRoutev6Test",
        "sai_route_test.RouteUpdateTest",
        "sai_route_test.RouteUpdatev6Test",
        "sai_route_test.RouteLPMRouteNexthopTest",
        "sai_route_test.RouteLPMRouteNexthopv6Test",
        "sai_route_test.RouteLPMRouteRifTest",
        "sai_route_test.RouteLPMRouteRifv6Test",
        "sai_route_test.SviMacFloodingTest",
        "sai_route_test.SviMacFloodingv6Test",
        "sai_route_test.SviDirectBroadcastTest",
        "sai_route_test.RemoveRouteV4Test",
        "sai_route_test.DefaultRouteV4Test",
        "sai_route_test.DefaultRouteV6Test",
        "sai_route_test.RouteSameSipDipv4Test",
        "sai_route_test.RouteSameSipDipv6Test",
        "sai_route_test.SviMacLearningTest",
        "sai_route_test.SviMacLearningV6Test",
        "sai_route_test.SviMacAgingTest",
        "sai_route_test.SviMacAgingV6Test",
        "sai_route_test.RouteDiffPrefixAddThenDeleteShorterV4Test",
        "sai_route_test.RouteDiffPrefixAddThenDeleteShorterV6Test",
        "sai_route_test.RouteDiffPrefixAddThenDeleteLongerV4Test",
        "sai_route_test.RouteDiffPrefixAddThenDeleteLongerV6Test",
        "sai_ecmp_test.EcmpHashFieldSportTestV4",
        "sai_ecmp_test.EcmpHashFieldSportTestV6",
        "sai_ecmp_test.EcmpHashFieldDportTestV4",
        "sai_ecmp_test.EcmpHashFieldDportTestV6",
        "sai_ecmp_test.EcmpHashFieldSIPTestV4",
        "sai_ecmp_test.EcmpHashFieldSIPTestV6",
        "sai_ecmp_test.EcmpHashFieldProtoTestV4",
        "sai_ecmp_test.EcmpHashFieldProtoTestV6",
        "sai_ecmp_test.IngressNoDiffTestV4",
        "sai_ecmp_test.RemoveLagEcmpTestV4",
        "sai_ecmp_test.RemoveLagEcmpTestV6",
        "sai_ecmp_test.RemoveAllNextHopMemeberTestV4",
        "sai_ecmp_test.RemoveNexthopGroupTestV4",
        "sai_ecmp_test.ReAddLagEcmpTestV4",
        "sai_ecmp_test.ReAddLagEcmpTestV6",
        "sai_ecmp_test.EcmpLagDisableTestV4",
        "sai_ecmp_test.EcmpLagDisableTestV6",
        "sai_ecmp_test.EcmpIngressDisableTestV4",
        "sai_ecmp_test.EcmpIngressDisableTestV6",
        "sai_ecmp_test.LagTwoLayersWithDiffHashOffsetTestV4",
        "sai_ecmp_test.LagTwoLayersWithDiffHashOffsetTestV6",
        "sai_ecmp_test.EcmpTwoLayersWithDiffHashOffsetTestV4",
        "sai_ecmp_test.EcmpTwoLayersWithDiffHashOffsetTestV6",
        "sai_ecmp_test.EcmpLagTwoLayersWithDiffHashOffsetTestV4",
        "sai_ecmp_test.EcmpLagTwoLayersWithDiffHashOffsetTestV6",
        "sai_ecmp_test.EcmpCoExistLagRouteV4",
        "sai_ecmp_test.EcmpCoExistLagRouteV6",
        "sai_ecmp_test.EcmpReuseLagRouteV4",
        "sai_ecmp_test.EcmpReuseLagRouteV6",
        "sai_tunnel_test.IPInIPTunnelDecapv4Inv4Test",
        "sai_tunnel_test.IPInIPTunnelDecapV6InV4Test",
        "sai_tunnel_test.IPInIPTunnelEncapv4Inv4Test",
        "sai_tunnel_test.IPInIPTunnelEncapv6Inv4Test",
        ]
