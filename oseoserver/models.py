# Copyright 2014 Ricardo Garcia Silva
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
Database models for pyoseo
"""

from __future__ import absolute_import
from datetime import datetime
from decimal import Decimal

from django.db import models

from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings as django_settings
import pytz
import pyxb
import pyxb.bundles.opengis.oseo_1_0 as oseo

from . import managers
from . import errors
from . import settings
from .constants import DeliveryOption
from .constants import MASSIVE_ORDER_REFERENCE
from .constants import OrderStatus
from .constants import OrderType
from .constants import Packaging
from .constants import Presentation
from .constants import Priority
from .constants import StatusNotification
from .utilities import _n


COLLECTION_CHOICES = [(c["name"], c["name"]) for
                      c in settings.get_collections()]

class AbstractDeliveryAddress(models.Model):
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    company_ref = models.CharField(max_length=50, blank=True)
    street_address = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, blank=True)
    post_box = models.CharField(max_length=50, blank=True)
    telephone = models.CharField(max_length=50, blank=True)
    fax = models.CharField(max_length=50, blank=True)

    class Meta:
        abstract = True

    def create_oseo_delivery_address(self):
        delivery_address = oseo.DeliveryAddressType()
        delivery_address.firstName = _n(self.first_name)
        delivery_address.lastName = _n(self.last_name)
        delivery_address.companyRef = _n(self.company_ref)
        delivery_address.postalAddress=pyxb.BIND()
        delivery_address.postalAddress.streetAddress = _n(self.street_address)
        delivery_address.postalAddress.city = _n(self.city)
        delivery_address.postalAddress.state = _n(self.state)
        delivery_address.postalAddress.postalCode = _n(self.postal_code)
        delivery_address.postalAddress.country = _n(self.country)
        delivery_address.postalAddress.postBox = _n(self.post_box)
        delivery_address.telephoneNumber = _n(self.telephone)
        delivery_address.facsimileTelephoneNumber = _n(self.fax)
        return delivery_address


class Batch(models.Model):
    # subFunction values for DescribeResultAccess operation
    ALL_READY = "allReady"
    NEXT_READY = "nextReady"

    order = models.ForeignKey("Order", null=True, related_name="batches")
    created_on = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True, blank=True)
    updated_on = models.DateTimeField(editable=False, blank=True, null=True)

    def status(self):
        order = {
            OrderStatus.SUBMITTED.value: 0,
            OrderStatus.ACCEPTED.value: 1,
            OrderStatus.IN_PRODUCTION.value: 2,
            OrderStatus.SUSPENDED.value: 3,
            OrderStatus.CANCELLED.value: 4,
            OrderStatus.COMPLETED.value: 5,
            OrderStatus.FAILED.value: 6,
            OrderStatus.TERMINATED.value: 7,
            OrderStatus.DOWNLOADED.value: 8,
        }
        item_statuses = set([oi.status for oi in self.order_items.all()])
        if OrderStatus.FAILED.value in item_statuses:
            status = OrderStatus.FAILED.value
        elif len(item_statuses) == 1:
            status = item_statuses.pop()
        elif any(item_statuses):
            status = list(item_statuses)[0]
            for st in item_statuses:
                if order[st] < order[status]:
                    status = st
        else:
            status = None
        return status

    def price(self):
        total = Decimal(0)
        return total

    def create_order_item(self, status, additional_status_info,
                          order_item_spec):
        item = OrderItem(
            batch=self,
            status=status,
            additional_status_info=additional_status_info,
            remark=order_item_spec["order_item_remark"],
            collection=order_item_spec["collection"],
            identifier=order_item_spec.get("identifier", ""),
            item_id=order_item_spec["item_id"]
        )
        item.save()
        for name, value in order_item_spec["option"].items():
            # assuming that the option has already been validated
            item.selected_options.add(SelectedOption(option=value,
                                                     value=value))
        for name, value in order_item_spec["scene_selection"].items():
            item.selected_scene_selection_options.add(
                SelectedSceneSelectionOption(option=name, value=value))
        delivery = order_item_spec["delivery_options"]
        if delivery is not None:
            copies = 1 if delivery["copies"] is None else delivery["copies"]
            sdo = SelectedDeliveryOption(
                customizable_item=item,

                delivery_type=None,
                delivery_details=None,

                annotation=delivery["annotation"],
                copies=copies,
                special_instructions=delivery["special_instructions"],
                option=delivery["type"]
            )
            sdo.save()
        if order_item_spec["payment"] is not None:
            item.selected_payment_option = SelectedPaymentOption(
                option=order_item_spec["payment"])
        item.save()
        return item

    def create_oseo_items_status(self):
        items_status = []
        for i in self.order_items.all():
            items_status.append(i.create_oseo_status_item_type())
        return items_status

    def get_completed_files(self, behaviour):
        last_time = self.order.last_describe_result_access_request
        order_delivery = self.order.selected_delivery_option.option
        completed = []
        if self.status() != OrderStatus.COMPLETED.value:
            # batch is either still being processed,
            # failed or already downloaded, so we don't care for it
            pass
        else:
            batch_complete_items = []
            order_items = self.order_items.all()
            for oi in order_items:
                try:
                    delivery = oi.selected_delivery_option.option
                except SelectedDeliveryOption.DoesNotExist:
                    delivery = order_delivery
                if delivery != DeliveryOption.ONLINE_DATA_ACCESS.value:
                    # getStatus only applies to items with onlinedataaccess
                    continue
                if oi.status == OrderStatus.COMPLETED.value:
                    if (last_time is None or behaviour == self.ALL_READY) or \
                            (behaviour == self.NEXT_READY and
                                     oi.completed_on >= last_time):
                        for f in oi.files.filter(available=True):
                            batch_complete_items.append((f, delivery))
            if self.order.packaging == Packaging.ZIP.value:
                if len(batch_complete_items) == len(order_items):
                    # the zip is ready, lets get only a single file
                    # because they all point to the same URL
                    completed.append(batch_complete_items[0])
                else:  # the zip is not ready yet
                    pass
            else:  # lets get each file that is complete
                completed = batch_complete_items
        return completed

    class Meta:
        verbose_name_plural = "batches"

    def __unicode__(self):
        return str("{}({})".format(self.__class__.__name__, self.id))


class CustomizableItem(models.Model):
    STATUS_CHOICES = [(status.value, status.value) for status in OrderStatus]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES,
                              default=OrderStatus.SUBMITTED.value,
                              help_text="initial status")
    additional_status_info = models.TextField(help_text="Additional "
                                              "information about the status",
                                              blank=True)
    mission_specific_status_info = models.TextField(help_text="Additional "
                                                    "information about the "
                                                    "status that is specific "
                                                    "to the mission",
                                                    blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True, blank=True)
    status_changed_on = models.DateTimeField(editable=False, blank=True,
                                             null=True)
    remark = models.TextField(help_text="Some specific remark about the item",
                              blank=True)

    def __unicode__(self):
        try:
            instance = Order.objects.get(id=self.id)
        except ObjectDoesNotExist:
            instance = OrderItem.objects.get(id=self.id)
        return instance.__unicode__()

    def create_oseo_delivery_options(self):
        """
        Create an OSEO DeliveryOptionsType

        :arg db_item: the database record model that has the delivery options
        :type db_item: pyoseo.models.CustomizableItem
        :return: A pyxb object with the delivery options
        """

        do = self.selected_delivery_option
        dot = oseo.DeliveryOptionsType()
        if do == DeliveryOption.ONLINE_DATA_ACCESS.value:
            dot.onlineDataAccess = pyxb.BIND()
            dot.onlineDataAccess.protocol = do.protocol
            pass
        elif do == DeliveryOption.ONLINE_DATA_DELIVERY.value:
            pass
        elif do == DeliveryOption.MEDIA_DELIVERY.value:
            pass
        else:
            pass  # raise some error


        try:
            do = self.selected_delivery_option
            dot = oseo.DeliveryOptionsType()
            try:
                oda = do.option.onlinedataaccess
                dot.onlineDataAccess = pyxb.BIND()
                dot.onlineDataAccess.protocol = oda.protocol
            except OnlineDataAccess.DoesNotExist:
                try:
                    odd = do.option.onlinedatadelivery
                    dot.onlineDataDelivery = pyxb.BIND()
                    dot.onlineDataDelivery.protocol = odd.protocol
                except OnlineDataDelivery.DoesNotExist:
                    md = do.option.mediadelivery
                    dot.mediaDelivery = pyxb.BIND()
                    dot.mediaDelivery.packageMedium = md.package_medium
                    dot.mediaDelivery.shippingInstructions = _n(
                        md.shipping_instructions)
            dot.numberOfCopies = _n(do.copies)
            dot.productAnnotation = _n(do.annotation)
            dot.specialInstructions = _n(do.special_instructions)
        except SelectedDeliveryOption.DoesNotExist:
            dot = None
        return dot


class Extension(models.Model):

    item = models.ForeignKey(CustomizableItem)
    text = models.CharField(
        max_length=255, blank=True,
        help_text="Custom extensions to the OSEO standard"
    )

    def __unicode__(self):
        return self.text


class DeliveryInformation(AbstractDeliveryAddress):
    order = models.OneToOneField("Order", related_name="delivery_information")

    def create_oseo_delivery_information(self):
        """Create an OSEO DeliveryInformationType"""
        del_info = oseo.DeliveryInformationType()
        optional_attrs = [self.first_name, self.last_name, self.company_ref,
                          self.street_address, self.city, self.state,
                          self.postal_code, self.country, self.post_box,
                          self.telephone, self.fax]
        if any(optional_attrs):
            del_info.mailAddress = oseo.DeliveryAddressType()
            del_info.mailAddress.firstName = _n(self.first_name)
            del_info.mailAddress.lastName = _n(self.last_name)
            del_info.mailAddress.companyRef = _n(self.company_ref)
            del_info.mailAddress.postalAddress = pyxb.BIND()
            del_info.mailAddress.postalAddress.streetAddress = _n(self.street_address)
            del_info.mailAddress.postalAddress.city = _n(self.city)
            del_info.mailAddress.postalAddress.state = _n(self.state)
            del_info.mailAddress.postalAddress.postalCode = _n(self.postal_code)
            del_info.mailAddress.postalAddress.country = _n(self.country)
            del_info.mailAddress.postalAddress.postBox = _n(self.post_box)
            del_info.mailAddress.telephoneNumber = _n(self.telephone)
            del_info.mailAddress.facsimileTelephoneNumber = _n(self.fax)
        for oa in self.onlineaddress_set.all():
            del_info.onlineAddress.append(oseo.OnlineAddressType())
            del_info.onlineAddress[-1].protocol = oa.protocol
            del_info.onlineAddress[-1].serverAddress = oa.server_address
            del_info.onlineAddress[-1].userName = _n(oa.user_name)
            del_info.onlineAddress[-1].userPassword = _n(oa.user_password)
            del_info.onlineAddress[-1].path = _n(oa.path)
        return del_info


class InvoiceAddress(AbstractDeliveryAddress):
    order = models.OneToOneField("Order", null=True,
                                 related_name="invoice_address")

    class Meta:
        verbose_name_plural = "invoice addresses"


class ItemProcessor(models.Model):
    PROCESSING_PARSE_OPTION = "option_parsing"
    PROCESSING_PROCESS_ITEM = "item_processing"
    PROCESSING_CLEAN_ITEM = "item_cleanup"

    python_path = models.CharField(
        max_length=255,
        default="oseoserver.orderpreparation.exampleorderprocessor."
                "ExampleOrderProcessor",
        help_text="Python import path to a custom class that is used to "
                  "process the order items. This class must conform to the "
                  "expected interface."
    )

    def export_params(self, processing_step):
        valid_params = dict()
        if processing_step == self.PROCESSING_PARSE_OPTION:
            qs = self.parameters.filter(use_in_option_parsing=True)
        elif processing_step == self.PROCESSING_PROCESS_ITEM:
            qs = self.parameters.filter(use_in_item_processing=True)
        else:
            qs = self.parameters.filter(use_in_item_cleanup=True)
        for param in qs:
            valid_params[param.name] = param.value
        return valid_params

    def __unicode__(self):
        return self.python_path


class OnlineAddress(models.Model):
    FTP = 'ftp'
    SFTP = 'sftp'
    FTPS = 'ftps'
    PROTOCOL_CHOICES = (
        (FTP, FTP),
        (SFTP, SFTP),
        (FTPS, FTPS),
    )
    delivery_information = models.ForeignKey('DeliveryInformation')
    protocol = models.CharField(max_length=20, default=FTP,
                                choices=PROTOCOL_CHOICES)
    server_address = models.CharField(max_length=255)
    user_name = models.CharField(max_length=50, blank=True)
    user_password = models.CharField(max_length=50, blank=True)
    path = models.CharField(max_length=1024, blank=True)

    class Meta:
        verbose_name_plural = 'online addresses'


class Order(CustomizableItem):
    MAX_ORDER_ITEMS = settings.get_max_order_items()

    PACKAGING_CHOICES = [(v.value, v.value) for v in Packaging]
    ORDER_TYPE_CHOICES = [(t.value, t.value) for t in OrderType]

    user = models.ForeignKey(django_settings.AUTH_USER_MODEL,
                             related_name="orders")
    order_type = models.CharField(
        max_length=30,
        default=OrderType.PRODUCT_ORDER.value,
        choices=ORDER_TYPE_CHOICES
    )


    last_describe_result_access_request = models.DateTimeField(null=True,
                                                               blank=True)
    reference = models.CharField(max_length=30,
                                 help_text="Some specific reference about "
                                           "this order",
                                 blank=True)
    packaging = models.CharField(max_length=30,
                                 choices=PACKAGING_CHOICES,
                                 blank=True)
    priority = models.CharField(
        max_length=30,
        choices=[(p.value, p.value) for p in Priority],
        blank=True
    )
    status_notification = models.CharField(
        max_length=10,
        default=StatusNotification.NONE.value,
        choices=[(n.value, n.value) for n in StatusNotification]
    )

    def show_batches(self):
        return ', '.join([str(b.id) for b in self.batches.all()])
    show_batches.short_description = 'available batches'


    def create_batch(self, item_status, additional_status_info,
                     *order_item_spec):
        batch = Batch()
        batch.save()
        for oi in order_item_spec:
            batch.create_order_item(item_status, additional_status_info,
                                    oi)
        self.batches.add(batch)
        return batch

    def create_oseo_order_monitor(
            self, presentation=Presentation.BRIEF.value):
        om = oseo.CommonOrderMonitorSpecification()
        if self.order_type == OrderType.MASSIVE_ORDER.value:
            om.orderType = OrderType.PRODUCT_ORDER.value
            om.orderReference = MASSIVE_ORDER_REFERENCE
        else:
            om.orderType = self.order_type
            om.orderReference = _n(self.reference)
        om.orderId = str(self.id)
        om.orderStatusInfo = oseo.StatusType(
            status=self.status,
            additionalStatusInfo=_n(self.additional_status_info),
            missionSpecificStatusInfo=_n(self.mission_specific_status_info)
        )
        om.orderDateTime = self.status_changed_on
        om.orderRemark = _n(self.remark)
        try:
            d = self.delivery_information.create_oseo_delivery_information()
            om.deliveryInformation = d
        except DeliveryInformation.DoesNotExist:
            pass
        try:
            om.invoiceAddress = \
                self.invoice_address.create_oseo_delivery_address()
        except InvoiceAddress.DoesNotExist:
            pass
        om.packaging = _n(self.packaging)
        # add any 'option' elements
        om.deliveryOptions = self.create_oseo_delivery_options()
        om.priority = _n(self.priority)
        if presentation == Presentation.FULL.value:
            if self.order_type == OrderType.PRODUCT_ORDER.value:
                batch = self.batches.get()
                sits = batch.create_oseo_items_status()
                om.orderItem.extend(sits)
            elif self.order_type == OrderType.SUBSCRIPTION_ORDER.value:
                for batch in self.batches.all()[1:]:
                    sits = batch.create_oseo_items_status()
                    om.orderItem.extend(sits)
            else:
                raise NotImplementedError
        return om


    def __unicode__(self):
        return '{}'.format(self.id)


class OrderPendingModeration(Order):
    objects = managers.OrderPendingModerationManager()

    class Meta:
        proxy = True
        verbose_name_plural = "orders pending moderation"



class ProductOrder(Order):

    def __unicode__(self):
        return "{}({})".format(self.__class__.__name__, self.id)


# TODO - Remove this model
class DerivedOrder(Order):
    pass

class MassiveOrder(DerivedOrder):

    def __unicode__(self):
        return "{}({})".format(self.__class__.__name__, self.id)


class SubscriptionOrder(DerivedOrder):
    begin_on = models.DateTimeField(help_text="Date and time for when the "
                                              "subscription should become "
                                              "active.")
    end_on = models.DateTimeField(help_text="Date and time for when the "
                                            "subscription should terminate.")

    def create_batch(self, item_status, additional_status_info,
                     *order_item_spec, **kwargs):
        """
        Create a batch for a subscription order.

        Subscription orders are different from normal product orders because
        the user is not supposed to be able to ask for the same collection
        twice.

        :param item_status:
        :param additional_status_info:
        :param order_item_spec:
        :return:
        """

        batch = Batch()
        batch.save()
        for oi in order_item_spec:
            collection = oi["collection"]
            previous_collections = [oi.collection for oi in
                                    batch.order_items.all()]
            if collection not in previous_collections:
                batch.create_order_item(item_status, additional_status_info,
                                        oi)
            else:
                raise errors.ServerError("Repeated collection: "
                                         "{}".format(collection))
        self.batches.add(batch)
        return batch

    def __unicode__(self):
        return "{}({})".format(self.__class__.__name__, self.id)


class TaskingOrder(DerivedOrder):

    def __unicode__(self):
        return "{}({})".format(self.__class__.__name__, self.id)


class OrderItem(CustomizableItem):
    batch = models.ForeignKey("Batch", related_name="order_items")
    collection = models.CharField(
        max_length=255,
        choices=COLLECTION_CHOICES
    )
    identifier = models.CharField(max_length=255, blank=True,
                                  help_text="identifier for this order item. "
                                            "It is the product Id in the "
                                            "catalog")
    item_id = models.CharField(max_length=80, help_text="Id for the item in "
                                                        "the order request")

    def export_options(self):
        valid_options = dict()
        for order_option in self.batch.order.selected_options.all():
            valid_options[order_option.option.name] = order_option.value
        for item_option in self.selected_options.all():
            valid_options[item_option.option.name] = item_option.value
        return valid_options

    def export_delivery_options(self):
        delivery = getattr(self, "selected_delivery_option", None)
        if delivery is None:
            delivery = getattr(self.batch.order, "selected_delivery_option")
        valid_delivery = {
            "copies": delivery.copies,
            "annotation": delivery.annotation,
            "special_instructions": delivery.special_instructions,
            "delivery_fee": delivery.option.delivery_fee,
        }
        if hasattr(delivery.option, "onlinedataaccess"):
            valid_delivery["delivery_type"] = "onlinedataaccess"
            valid_delivery["protocol"] = \
                delivery.option.onlinedataaccess.protocol
        elif hasattr(delivery.option, "onlinedatadelivery"):
            valid_delivery["delivery_type"] = "onlinedatadelivery"
            valid_delivery["protocol"] = \
                delivery.option.onlinedatadelivery.protocol
        else:  # media delivery
            valid_delivery["delivery_type"] = "mediadelivery"
        return valid_delivery

    def create_oseo_status_item_type(self):
        """
        Create a CommonOrderStatusItemType element
        :return:
        """
        sit = oseo.CommonOrderStatusItemType()
        # TODO - add the other optional elements
        sit.itemId = str(self.item_id)
        # oi.identifier is guaranteed to be non empty for
        # normal product orders and for subscription batches
        sit.productId = self.identifier
        sit.productOrderOptionsId = "Options for {} {}".format(
            self.collection.name, self.batch.order.order_type)
        sit.orderItemRemark = _n(self.remark)
        sit.collectionId = _n(self.collection_id)
        # add any 'option' elements that may be present
        # add any 'sceneSelection' elements that may be present
        sit.deliveryOptions = self.create_oseo_delivery_options()
        # add any 'payment' elements that may be present
        # add any 'extension' elements that may be present
        sit.orderItemStatusInfo = oseo.StatusType()
        sit.orderItemStatusInfo.status = self.status
        sit.orderItemStatusInfo.additionalStatusInfo = \
            _n(self.additional_status_info)
        sit.orderItemStatusInfo.missionSpecificStatusInfo= \
            _n(self.mission_specific_status_info)
        return sit

    def __unicode__(self):
        return str(self.item_id)


class OseoFile(models.Model):
    order_item = models.ForeignKey("OrderItem", related_name="files")
    created_on = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length=255, help_text="URL where this file "
                                                     "is available")
    expires_on = models.DateTimeField(null=True, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    available = models.BooleanField(default=False)
    downloads = models.SmallIntegerField(default=0,
                                         help_text="Number of times this "
                                                   "order item has been "
                                                   "downloaded.")

    def can_be_deleted(self):
        result = False
        now = datetime.now(pytz.utc)
        if self.expires_on < now:
            result = True
        else:
            user = self.order_item.batch.order.user
            if self.downloads > 0 and user.delete_downloaded_files:
                result = True
        return result

    def __unicode__(self):
        return self.url


#class PaymentOption(AbstractOption):
#
#    def __unicode__(self):
#        return self.name


class ProcessorParameter(models.Model):
    item_processor = models.ForeignKey("ItemProcessor",
                                       related_name="parameters")
    name = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    use_in_option_parsing = models.BooleanField(default=False)
    use_in_item_processing = models.BooleanField(default=False)
    use_in_item_cleanup = models.BooleanField(default=False)

    def __unicode__(self):
        return self.name


#class SceneSelectionOption(AbstractOption):
#
#    def __unicode__(self):
#        return self.name


#class SceneSelectionOptionChoice(AbstractOptionChoice):
#    scene_selection_option = models.ForeignKey('SceneSelectionOption',
#                                               related_name='choices')


class SelectedOption(models.Model):
    customizable_item = models.ForeignKey('CustomizableItem',
                                          related_name='selected_options')
    #option = models.ForeignKey('Option')
    option = models.CharField(max_length=255)
    value = models.CharField(max_length=255, help_text='Value for this option')

    def __unicode__(self):
        return self.value


class SelectedPaymentOption(models.Model):
    order_item = models.OneToOneField('OrderItem',
                                      related_name='selected_payment_option',
                                      null=True,
                                      blank=True)
    #option = models.ForeignKey('PaymentOption')
    option = models.CharField(max_length=255)

    def __unicode__(self):
        return self.option.name


class SelectedSceneSelectionOption(models.Model):
    order_item = models.ForeignKey(
        'OrderItem',
        related_name='selected_scene_selection_options'
    )
    #option = models.ForeignKey('SceneSelectionOption')
    option = models.CharField(max_length=255)
    value = models.CharField(max_length=255,
                             help_text='Value for this option')

    def __unicode__(self):
        return self.value


class SelectedDeliveryOption(models.Model):
    DELIVERY_CHOICES = [(v.value, v.value) for v in DeliveryOption]

    customizable_item = models.OneToOneField(
        'CustomizableItem',
        related_name='selected_delivery_option',
        blank=True,
        null=True
    )
    #option = models.ForeignKey('DeliveryOption')
    delivery_type = models.CharField(
        max_length=30,
        choices=DELIVERY_CHOICES,
        default=DeliveryOption.ONLINE_DATA_ACCESS.value,
        help_text="Type of delivery that has been specified"
    )
    delivery_details = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        help_text="A comma separated string with further details pertaining "
                  "the selected delivery type, such as the protocol to use "
                  "for online data delivery. Each delivery type expects a "
                  "concrete string format."
    )
    copies = models.PositiveSmallIntegerField(null=True, blank=True)
    annotation = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)

    def __unicode__(self):
        return self.option.__unicode__()


class SubscriptionBatch(Batch):
    timeslot = models.DateTimeField()
    collection = models.CharField(
        max_length=255,
        choices=COLLECTION_CHOICES
    )

    class Meta:
        verbose_name_plural = "subscription batches"

    def __unicode__(self):
        return str("{}({})".format(self.__class__.__name__, self.id))


#class AbstractOption(models.Model):
#    name = models.CharField(max_length=100)
#    description = models.CharField(max_length=255, blank=True)
#    multiple_entries = models.BooleanField(
#        default=False,
#        help_text="Can this option have multiple selections?"
#    )
#
#    class Meta:
#        abstract = True


#class AbstractOptionChoice(models.Model):
#    value = models.CharField(max_length=255, help_text="Value for this option")
#
#    class Meta:
#        abstract = True
#
#    def __unicode__(self):
#        return self.value


#class DeliveryOption(models.Model):
#    PROTOCOL_CHOICES = [(protocol.value, protocol.value) for protocol in
#                      constants.DeliveryOptionProtocol]
#    delivery_fee = models.DecimalField(default=Decimal(0), max_digits=5,
#                                       decimal_places=2)
#
#    def child_instance(self):
#        try:
#            instance = OnlineDataAccess.objects.get(id=self.id)
#        except ObjectDoesNotExist:
#            try:
#                instance = OnlineDataDelivery.objects.get(id=self.id)
#            except ObjectDoesNotExist:
#                try:
#                    instance = MediaDelivery.objects.get(id=self.id)
#                except ObjectDoesNotExist:
#                    instance = self
#        return instance
#
#    def __unicode__(self):
#        instance = self.child_instance()
#        return instance.__unicode__()


#class MediaDelivery(DeliveryOption):
#    MEDIUM_CHOICES = [(m.value, m.value) for m in constants.DeliveryMedium]
#
#    package_medium = models.CharField(
#        max_length=20,
#        choices=MEDIUM_CHOICES,
#        blank=True
#    )
#    EACH_READY = "as each product is ready"
#    ALL_READY = "once all products are ready"
#    OTHER = "other"
#    SHIPPING_CHOICES = (
#        (EACH_READY, EACH_READY),
#        (ALL_READY, ALL_READY),
#        (OTHER, OTHER),
#    )
#    shipping_instructions = models.CharField(
#        max_length=100,
#        choices=SHIPPING_CHOICES,
#        blank=True
#    )
#
#    class Meta:
#        verbose_name_plural = "media deliveries"
#        unique_together = ("package_medium", "shipping_instructions")
#
#    def __unicode__(self):
#        return "{}:{}:{}".format(self.__class__.__name__, self.package_medium,
#                                 self.shipping_instructions)


#class Option(AbstractOption):
#
#    def _get_choices(self):
#        return ", ".join([c.value for c in self.choices.all()])
#    available_choices = property(_get_choices)
#
#    def __unicode__(self):
#        return self.name


#class OptionChoice(AbstractOptionChoice):
#    option = models.ForeignKey('Option', related_name='choices')


#class OnlineDataAccess(DeliveryOption):
#    protocol = models.CharField(max_length=20,
#                                choices=DeliveryOption.PROTOCOL_CHOICES,
#                                default=DeliveryOption.FTP,
#                                unique=True)
#
#    class Meta:
#        verbose_name_plural = 'online data accesses'
#
#    def __unicode__(self):
#        return "{}:{}".format(self.__class__.__name__, self.protocol)


#class OnlineDataDelivery(DeliveryOption):
#    protocol = models.CharField(
#        max_length=20,
#        choices=DeliveryOption.PROTOCOL_CHOICES,
#        default=DeliveryOption.FTP,
#        unique=True
#    )
#
#    class Meta:
#        verbose_name_plural = 'online data deliveries'
#
#    def __unicode__(self):
#        return "{}:{}".format(self.__class__.__name__, self.protocol)


