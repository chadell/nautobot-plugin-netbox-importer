"""Abstract base DiffSync adapter class for code shared by NetBox and Nautobot adapters."""

from collections import defaultdict
from typing import MutableMapping, Union
from uuid import UUID

from diffsync import Diff, DiffSync, DiffSyncFlags, DiffSyncModel
from diffsync.exceptions import ObjectAlreadyExists
from pydantic.error_wrappers import ValidationError
import structlog

import nautobot_netbox_importer.diffsync.models as n2nmodels


class N2NDiffSync(DiffSync):
    """Generic DiffSync adapter for working with NetBox/Nautobot data models."""

    _data_by_pk: MutableMapping[str, MutableMapping[Union[UUID, int], DiffSyncModel]]

    logger = structlog.get_logger()

    contenttype = n2nmodels.ContentType

    # Users and auth
    group = n2nmodels.Group
    objectpermission = n2nmodels.ObjectPermission
    permission = n2nmodels.Permission
    token = n2nmodels.Token
    user = n2nmodels.User
    userconfig = n2nmodels.UserConfig

    # Circuits
    circuit = n2nmodels.Circuit
    circuittermination = n2nmodels.CircuitTermination
    circuittype = n2nmodels.CircuitType
    provider = n2nmodels.Provider

    # DCIM
    cable = n2nmodels.Cable
    consoleport = n2nmodels.ConsolePort
    consoleporttemplate = n2nmodels.ConsolePortTemplate
    consoleserverport = n2nmodels.ConsoleServerPort
    consoleserverporttemplate = n2nmodels.ConsoleServerPortTemplate
    device = n2nmodels.Device
    devicebay = n2nmodels.DeviceBay
    devicebaytemplate = n2nmodels.DeviceBayTemplate
    devicerole = n2nmodels.DeviceRole
    devicetype = n2nmodels.DeviceType
    frontport = n2nmodels.FrontPort
    frontporttemplate = n2nmodels.FrontPortTemplate
    interface = n2nmodels.Interface
    interfacetemplate = n2nmodels.InterfaceTemplate
    inventoryitem = n2nmodels.InventoryItem
    manufacturer = n2nmodels.Manufacturer
    platform = n2nmodels.Platform
    powerfeed = n2nmodels.PowerFeed
    poweroutlet = n2nmodels.PowerOutlet
    poweroutlettemplate = n2nmodels.PowerOutletTemplate
    powerpanel = n2nmodels.PowerPanel
    powerport = n2nmodels.PowerPort
    powerporttemplate = n2nmodels.PowerPortTemplate
    rack = n2nmodels.Rack
    rackgroup = n2nmodels.RackGroup
    rackreservation = n2nmodels.RackReservation
    rackrole = n2nmodels.RackRole
    rearport = n2nmodels.RearPort
    rearporttemplate = n2nmodels.RearPortTemplate
    region = n2nmodels.Region
    site = n2nmodels.Site
    virtualchassis = n2nmodels.VirtualChassis

    # Extras
    configcontext = n2nmodels.ConfigContext
    customfield = n2nmodels.CustomField
    customlink = n2nmodels.CustomLink
    exporttemplate = n2nmodels.ExportTemplate
    jobresult = n2nmodels.JobResult
    status = n2nmodels.Status
    tag = n2nmodels.Tag
    taggeditem = n2nmodels.TaggedItem
    webhook = n2nmodels.Webhook

    # IPAM
    aggregate = n2nmodels.Aggregate
    ipaddress = n2nmodels.IPAddress
    prefix = n2nmodels.Prefix
    rir = n2nmodels.RIR
    role = n2nmodels.Role
    routetarget = n2nmodels.RouteTarget
    service = n2nmodels.Service
    vlan = n2nmodels.VLAN
    vlangroup = n2nmodels.VLANGroup
    vrf = n2nmodels.VRF

    # Tenancy
    tenantgroup = n2nmodels.TenantGroup
    tenant = n2nmodels.Tenant

    # Virtualization
    clustertype = n2nmodels.ClusterType
    clustergroup = n2nmodels.ClusterGroup
    cluster = n2nmodels.Cluster
    virtualmachine = n2nmodels.VirtualMachine
    vminterface = n2nmodels.VMInterface

    top_level = (
        # "contenttype", Not synced, as these are hard-coded in NetBox/Nautobot
        "customfield",
        "permission",
        "group",
        "user",
        "objectpermission",
        "token",
        "userconfig",
        # "status", Not synced, as these are hard-coded in NetBox/Nautobot
        # Need Tenant and TenantGroup before we can populate Sites
        "tenantgroup",
        "tenant",  # Not all Tenants belong to a TenantGroup
        "region",
        "site",  # Not all Sites belong to a Region
        "manufacturer",
        "devicetype",
        "consoleporttemplate",
        "consoleserverporttemplate",
        "powerporttemplate",
        "poweroutlettemplate",
        "rearporttemplate",
        "frontporttemplate",
        "interfacetemplate",
        "devicebaytemplate",
        "devicerole",
        "platform",
        "clustertype",
        "clustergroup",
        "cluster",
        "provider",
        "circuittype",
        "circuit",
        "circuittermination",
        "rackgroup",
        "rackrole",
        "rack",
        "rackreservation",
        "powerpanel",
        "powerfeed",
        "routetarget",
        "vrf",
        "rir",
        "aggregate",
        "role",
        "vlangroup",
        "vlan",
        "prefix",
        # Lots of pre-requisites for constructing a Device!
        "device",
        "devicebay",
        "inventoryitem",
        "virtualchassis",
        "virtualmachine",
        "consoleport",
        "consoleserverport",
        "powerport",
        "poweroutlet",
        "rearport",
        "frontport",
        "interface",
        "vminterface",
        # Reference loop: Device -> IPAddress (primaryip), IPAddress -> Interface (assigned_object), Interface -> Device
        # Interface comes after Device because it MUST have a Device to be created;
        # IPAddress comes after Interface because we use the assigned_object as part of the IP's unique ID.
        # We will fixup the Device->primaryip reference in fixup_data_relations()
        "ipaddress",
        "cable",
        "service",
        # The below have no particular upward dependencies, they're just logically kind of the last to do.
        "tag",
        "configcontext",
        "customlink",
        "exporttemplate",
        "webhook",
        "taggeditem",
        "jobresult",
    )

    def __init__(self, *args, **kwargs):
        """Initialize this container, including its PK-indexed alternate data store."""
        super().__init__(*args, **kwargs)
        self._data_by_pk = defaultdict(dict)
        self._sync_summary = None

    def sync_summary(self):
        """Get the summary of the last sync, if any."""
        return self._sync_summary

    def add(self, obj: DiffSyncModel):
        """Add a DiffSync model to the store, as well as registering it by PK for fast later retrieval."""
        # Store it by PK *before* we attempt to add it to the parent datastore,
        # in case we have duplicate objects with the same unique_id but different PKs.
        modelname = obj.get_type()
        if obj.pk in self._data_by_pk[modelname]:
            raise ObjectAlreadyExists(f"Object {modelname} with pk {obj.pk} already loaded")
        self._data_by_pk[modelname][obj.pk] = obj
        super().add(obj)

    def fixup_data_relations(self):
        """Iterate once more over all models and fix up any leftover FK relations."""
        for name in self.top_level:
            instances = self.get_all(name)
            if not instances:
                self.logger.info("No instances to review", model=name)
            else:
                self.logger.info(f"Reviewing all {len(instances)} instances", model=name)
            for diffsync_instance in instances:
                for fk_field, target_name in diffsync_instance.fk_associations().items():
                    value = getattr(diffsync_instance, fk_field)
                    if not value:
                        continue
                    if "*" in target_name:
                        target_content_type_field = target_name[1:]
                        target_content_type = getattr(diffsync_instance, target_content_type_field)
                        target_name = target_content_type["model"]
                    target_class = getattr(self, target_name)
                    if "pk" in value:
                        new_value = self.get_fk_identifiers(diffsync_instance, target_class, value["pk"])
                        if isinstance(new_value, (UUID, int)):
                            self.logger.error(
                                "Still unable to resolve reference?",
                                source=diffsync_instance,
                                target=target_name,
                                pk=new_value,
                            )
                        else:
                            self.logger.debug(
                                "Replacing forward reference with identifiers", pk=value["pk"], identifiers=new_value
                            )
                            setattr(diffsync_instance, fk_field, new_value)

    def get_fk_identifiers(self, source_object, target_class, pk):
        """Helper to load_record: given a class and a PK, get the identifiers of the given instance."""
        target_record = self.get_by_pk(target_class, pk)
        if not target_record:
            self.logger.debug(
                "Unresolved forward reference, will require later fixup",
                source_class=source_object.get_type(),
                target_class=target_class.get_type(),
                pk=pk,
            )
            return pk
        return target_record.get_identifiers()

    def get_by_pk(self, obj, pk):
        """Retrieve a previously loaded object by its primary key."""
        if isinstance(obj, str):
            modelname = obj
        else:
            modelname = obj.get_type()
        return self._data_by_pk[modelname].get(pk)

    def make_model(self, diffsync_model, data):
        """Instantiate and add the given diffsync_model."""
        try:
            instance = diffsync_model(**data, diffsync=self)
        except ValidationError as exc:
            self.logger.error(str(exc))
            return None
        try:
            self.add(instance)
        except ObjectAlreadyExists:
            self.logger.warning("Apparent duplicate object encountered", model=instance)
        return instance

    def sync_from(self, source: DiffSync, diff_class: Diff = Diff, flags: DiffSyncFlags = DiffSyncFlags.NONE):
        """Synchronize data from the given source DiffSync object into the current DiffSync object."""
        self._sync_summary = None
        return super().sync_from(source, diff_class=diff_class, flags=flags)

    def sync_complete(
        self,
        source: DiffSync,
        diff: Diff,
        flags: DiffSyncFlags = DiffSyncFlags.NONE,
        logger: structlog.BoundLogger = None,
    ):
        """Callback invoked after completing a sync operation in which changes occurred."""
        self._sync_summary = diff.summary()
        self.logger.info("Summary of changes", summary=self._sync_summary)
        return super().sync_complete(source, diff, flags=flags, logger=logger)