# Copyright 2015 Ricardo Garcia Silva
#
# Licensed under the Apache License, Version 2.0 (the "License");
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
A default order processing module for oseoserver. It does nothing, but
serves as an example of the API that oseoserver expects to find on a real
implementation.
"""

from __future__ import absolute_import
import logging

from lxml import etree
from pyxb import BIND
from pyxb.bundles.opengis import csw_2_0_2 as csw
from pyxb.bundles.opengis.iso19139.v20070417 import gmd
from pyxb.bundles.opengis.iso19139.v20070417 import gco
import requests

from .. import settings
from .. import errors
from .. import constants


logger = logging.getLogger(__name__)


class ExampleOrderProcessor(object):

    def __init__(self, **kwargs):
        pass

    def parse_option(self, name, value):
        """Parse an option and extract its value.

        This method will be called by oseoserver for each selected...

        :param name:
        :param value:
        :return:
        """

        logger.debug("locals: {}".format(locals()))
        #parsed_value = value.text
        parsed_value = value
        logger.debug("name: {}".format(name))
        logger.debug("value: {}".format(value))
        logger.debug("parsed_value: {}".format(parsed_value))
        return parsed_value

    def get_collection_id(self, item_id):
        """Determine the collection identifier for the specified item.

        This method is used when the requested order item does not provide the
        optional 'collectionId' element. It searched all of the defined
        catalogue endpoints and determines the collection for the
        specified item.

        The example shown here assumes that the input `item_id` is the
        identifier for a record in a CSW catalogue.

        Parameters
        ----------
        item_id: str
            Identifier of an order item that belongs to the collection to
            find

        Returns
        -------
        str
            Identifier of the collection
        """

        request_headers = {"Content-Type": "application/xml"}
        ns = {"gmd": gmd.Namespace.uri(), "gco": gco.Namespace.uri(),}
        req = csw.GetRecordById(
            service="CSW",
            version="2.0.2",
            ElementSetName="summary",
            outputSchema=ns["gmd"],
            Id=[BIND(item_id)]
        )
        query_path = ("gmd:MD_Metadata/gmd:parentIdentifier/"
                      "gco:CharacterString/text()")
        for collection in settings.get_collections():
            response = requests.post(
                collection["catalogue_endpoint"],
                data=req.toxml(),
                headers=request_headers
            )
            if response.status_code == 200:
                r = etree.fromstring(response.text.encode(constants.ENCODING))
                id_container = r.xpath(query_path, namespaces=ns)
                if any(id_container):
                    collection_id = id_container[0]
                    break
        else:
            raise errors.OseoServerError("Could not retrieve collection "
                                         "id for item {!r}".format(item_id))
        return collection_id

    def get_subscription_batch_identifiers(self, timeslot, collection,
                                           **kwargs):
        """
        Find the identifiers for resources of a subscription batch

        :param timeslot:
        :type timeslot: datetime.datetime
        :param collection:
        :type collection: basestring
        :return:
        """

        return ["fake_identifier"]

    def process_item_online_access(identifier, item_id, order_id, user_name,
                                   packaging, options, delivery_options,
                                   **kwargs):
        """
        Process an item that has been ordered.

        According to the selected options, a single item can in fact result
        in multiple output files. For example, a multiband dataset may be
        split into its sub bands.

        :param identifier:
        :type identifier:
        :param order_id:
        :type order_id:
        :param user_name:
        :type user_name:
        :param packaging:
        :type packaging: bool
        :param options:
        :type options: dict()
        :param delivery_options:
        :type delivery_options: dict()
        :return: A list with the URI of the processed item(s) and a
            string with additional details. Each URI is relative to
            the url pattern declared in the show_item urlconf entry
            in oseoserver.urls
        :rtype: ([string], string)
        """

        logger.debug("fake processing of an order item")
        logger.debug("arguments: {}".format(locals()))
        #file_name = None
        #details = "The item failed because this is a fake processor"
        file_name = "fakeorder"
        details = "Pretending to be a file"
        return [file_name], details

    def package_files(self, packaging, domain, delete_paths=True,
                      site_name=None, server_port=None, file_urls=[],
                      **kwargs):
        """
        Create a packaged archive file with the input file_urls.

        :param packaging:
        :param domain:
        :param delete_paths:
        :param site_name:
        :param server_port:
        :param file_urls:
        :param kwargs:
        :return:
        """

        output_url = "fake_url_for_the_package"
        return output_url

    def clean_files(self, file_urls=[], **kwargs):
        """
        Delete the files that match the input file_urls from the filesystem.

        This method has the responsability of finding the files that are
        represented by each file_url and deleting them.

        :param file_urls: A sequence containing file URLs
        :type file_urls: [str]
        :param kwargs:
        :return: Nothing
        """

        pass

