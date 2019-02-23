import cgi
import json
import time
import urllib
from copy import deepcopy

from stream_alert.shared.publisher import AlertPublisher, Register
from stream_alert.shared.description import RuleDescriptionParser

RAUSCH = '#ff5a5f'
BABU = '#00d1c1'
LIMA = '#8ce071'
HACKBERRY = '#7b0051'


@Register
class Summary(AlertPublisher):
    """Adds a brief summary with the rule triggered, author, description, and time

    To customize the behavior of this Publisher, it is recommended to subclass this and override
    parameters as necessary. For example, an implementation could override _GITHUB_REPO_URL with
    the URL appropriate for the organization using StreamAlert.
    """

    _GITHUB_REPO_URL = 'https://github.com/airbnb/streamalert'
    _SEARCH_PATH = '/search'
    _RULES_PATH = '/rules'

    def publish(self, alert, publication):
        rule_name = alert.rule_name
        rule_description = alert.rule_description
        rule_presentation = RuleDescriptionParser.present(rule_description)

        author = rule_presentation['author']

        return {
            'slack.text': 'Rule triggered',
            'slack.attachments': [
                {
                    'fallback': 'Rule triggered: {}'.format(rule_name),
                    'color': self._color(),
                    'author_name': author,
                    'author_link': self._author_url(author),
                    'author_icon': self._author_icon(author),
                    'title': rule_name,
                    'title_link': self._title_url(rule_name),
                    'text': cgi.escape(rule_presentation['description']),
                    'fields': map(
                        lambda(key): {'title': key, 'value': rule_presentation['fields'][key]},
                        rule_presentation['fields'].keys()
                    ),
                    'image_url': '',
                    'thumb_url': '',
                    'footer': '',
                    'footer_icon': '',
                    'ts': time.mktime(alert.created.timetuple()) if alert.created else '',
                    'mrkdwn_in': [],
                },
            ],

            # This information is passed-through to future publishers.
            '_previous_publication': publication,
        }

    @staticmethod
    def _color():
        """The color of this section"""
        return RAUSCH

    @classmethod
    def _author_url(cls, _):
        """When given an author name, returns a clickable link, if any"""
        return ''

    @classmethod
    def _author_icon(cls, _):
        """When given an author name, returns a URL to an icon, if any"""
        return ''

    @classmethod
    def _title_url(cls, rule_name):
        """When given the rule_name, returns a clickable link, if any"""

        # It's actually super hard to generate a exact link to a file just from the rule_name,
        # because the rule/ directory files are not deployed with the publishers in the alert
        # processor.
        # Instead, we send them to Github with a formatted query string that is LIKELY to
        # find the correct file.
        #
        # If you do not want URLs to show up, simply override this method and return empty string.
        return '{}{}?{}'.format(
            cls._GITHUB_REPO_URL,
            cls._SEARCH_PATH,
            urllib.urlencode({
                'q': '{} path:{}'.format(rule_name, cls._RULES_PATH)
            })
        )


@Register
class AttachRuleInfo(AlertPublisher):
    """This publisher adds a slack attachment with fields from the rule's description

    It can include such fields as "reference" or "playbook" but will NOT include the description
    or the author.
    """

    def publish(self, alert, publication):
        new_publication = deepcopy(publication)
        new_publication['slack.attachments'] = new_publication.get('slack.attachments', [])

        rule_description = alert.rule_description
        rule_presentation = RuleDescriptionParser.present(rule_description)

        new_publication['slack.attachments'].append({
            'color': self._color(),
            'fields': map(
                lambda (key): {'title': key, 'value': rule_presentation['fields'][key]},
                rule_presentation['fields'].keys()
            )
        })

        return new_publication

    @staticmethod
    def _color():
        return LIMA


@Register
class AttachPublication(AlertPublisher):
    """A publisher run after PrettyLayout that attaches previous publications as an attachment"""

    def publish(self, alert, publication):
        if '_previous_publication' not in publication or 'slack.attachments' not in publication:
            # This publisher cannot be run except immediately after PrettyLayout
            return publication

        new_publication = deepcopy(publication)

        publication_block = '```\n{}\n```'.format(
            json.dumps(
                publication['_previous_publication'],
                indent=2,
                sort_keys=True,
                separators=(',', ': ')
            )
        )

        new_publication['slack.attachments'].append({
            'color': self._color(),
            'title': 'Alert Data:',
            'text': cgi.escape(publication_block),
            'mrkdwn_in': ['text'],
        })

        return new_publication

    @staticmethod
    def _color():
        return BABU


@Register
class AttachFullRecord(AlertPublisher):
    """This publisher attaches slack attachments generated from the Alert's full record

    The full record is likely to be significantly longer than the slack max messages size.
    So we cut up the record by rows and send it as a series of 1 or more attachments.
    The attachments are rendered in slack in a way such that a mouse drag and copy will
    copy the entire JSON in-tact.

    The first attachment is slightly different as it includes the source entity where the
    record originated from. The last attachment includes a footer.
    """
    _SLACK_MAXIMUM_ATTACHMENT_CHARACTER_LENGTH = 4000

    # Reserve space at the beginning and end of the attachment text for backticks and newlines
    _LENGTH_PADDING = 10

    def publish(self, alert, publication):
        new_publication = deepcopy(publication)
        new_publication['slack.attachments'] = new_publication.get('slack.attachments', [])

        # Generate the record and then dice it up into parts
        record_document = json.dumps(alert.record, indent=2, sort_keys=True, separators=(',', ': '))

        # Escape the document FIRST because it can increase character length which can throw off
        # document slicing
        record_document = cgi.escape(record_document)
        record_document_lines = record_document.split('\n')

        def make_attachment(document, is_first, is_last):

            footer = ''
            if is_last:
                footer_url = self._source_service_url(alert.source_service)
                if footer_url:
                    footer = 'via <{}|{}>'.format(footer_url, alert.source_service)
                else:
                    'via {}'.format(alert.source_service)

            return {
                'color': self._color(),
                'author': alert.source_entity if is_first else '',
                'title': 'Record' if is_first else '',
                'text': '```\n{}\n```'.format(document),
                'fields': [
                    {
                        "title": "Alert Id",
                        "value": alert.alert_id,
                    }
                ] if is_last else [],
                'footer': footer,
                'footer_icon': self._footer_icon_from_service(alert.source_service),
                'mrkdwn_in': ['text'],
            }

        character_limit = self._SLACK_MAXIMUM_ATTACHMENT_CHARACTER_LENGTH - self._LENGTH_PADDING
        is_first_document = True
        next_document = ''
        while len(record_document_lines) > 0:
            # Loop, removing one line at a time and attempting to attach it to the next document
            # When the next document nears the maximum attachment size, it is flushed, generating
            # a new attachment, and the document is reset before the loop pops off the next line.

            next_item_length = len(record_document_lines[0])
            next_length = next_item_length + len(next_document)
            if next_document and next_length > character_limit:
                # Do not pop off the item just yet.
                new_publication['slack.attachments'].append(
                    make_attachment(next_document, is_first_document, False)
                )
                next_document = ''
                is_first_document = False

            next_document += '\n' + record_document_lines.pop(0)

        # Attach last document, if any remains
        if next_document:
            new_publication['slack.attachments'].append(
                make_attachment(next_document, is_first_document, True)
            )

        return new_publication

    @staticmethod
    def _color():
        return HACKBERRY

    @staticmethod
    def _source_service_url(source_service):
        """A best-effort guess at the AWS dashboard link for the requested service."""
        return 'https://console.aws.amazon.com/{}/home'.format(source_service)

    @staticmethod
    def _footer_icon_from_service(_):
        """Returns the URL of an icon, given an AWS service"""
        return ''
