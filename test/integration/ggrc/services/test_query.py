# coding: utf-8

# Copyright (C) 2016 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for /query api endpoint."""

from datetime import datetime
from operator import itemgetter
from flask import json
from nose.plugins.skip import SkipTest

from ggrc import db
from ggrc.models import CustomAttributeDefinition as CAD

from integration.ggrc.converters import TestCase
from integration.ggrc.models import factories


# to be moved into converters.query_helper
DATE_FORMAT_REQUEST = "%m/%d/%Y"
DATE_FORMAT_RESPONSE = "%Y-%m-%d"


# pylint: disable=super-on-old-class; false positive
class BaseQueryAPITestCase(TestCase):
  """Base class for /query api tests with utility methods."""

  def setUp(self):
    """Log in before performing queries."""
    # we don't call super as TestCase.setUp clears the DB
    # super(BaseQueryAPITestCase, self).setUp()
    self.client.get("/login")

  def _post(self, data):
    """Make a POST to /query endpoint."""
    if not isinstance(data, list):
      data = [data]
    headers = {"Content-Type": "application/json", }
    return self.client.post("/query", data=json.dumps(data), headers=headers)

  def _get_first_result_set(self, data, *keys):
    """Post data, get response, get values from it like in obj["a"]["b"]."""
    response = self._post(data)
    self.assert200(response)
    result = json.loads(response.data)[0]
    for key in keys:
      result = result.get(key)
      self.assertIsNot(result, None)
    return result

  @staticmethod
  def _make_query_dict(object_name, type_=None, expression=None, limit=None,
                       order_by=None):
    """Make a dict with query for object_name with optional parameters."""
    def make_filter_expression(expression):
      """Convert a three-tuple to a simple expression filter."""
      left, op_name, right = expression
      return {"left": left, "op": {"name": op_name}, "right": right}

    query = {
        "object_name": object_name,
        "filters": {"expression": {}},
    }
    if type_:
      query["type"] = type_
    if expression:
      query["filters"]["expression"] = make_filter_expression(expression)
    if limit:
      query["limit"] = limit
    if order_by:
      query["order_by"] = order_by
    return query


# pylint: disable=too-many-public-methods
class TestAdvancedQueryAPI(BaseQueryAPITestCase):
  """Basic tests for /query api."""

  @classmethod
  def setUpClass(cls):
    """Set up test cases for all tests."""
    TestCase.clear_data()
    # This imported file could be simplified a bit to speed up testing.
    cls._import_file("data_for_export_testing.csv")

  def test_basic_query_eq(self):
    """Filter by = operator."""
    title = "Cat ipsum 1"
    programs = self._get_first_result_set(
        self._make_query_dict("Program", expression=["title", "=", title]),
        "Program",
    )

    self.assertEqual(programs["count"], 1)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertEqual(programs["values"][0]["title"], title)

  def test_basic_query_in(self):
    """Filter by ~ operator."""
    title_pattern = "1"
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["title", "~", title_pattern]),
        "Program",
    )

    self.assertEqual(programs["count"], 12)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertTrue(all(title_pattern in program["title"]
                        for program in programs["values"]))

  def test_basic_query_ne(self):
    """Filter by != operator."""
    title = "Cat ipsum 1"
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["title", "!=", title]),
        "Program",
    )

    self.assertEqual(programs["count"], 22)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertTrue(all(program["title"] != title
                        for program in programs["values"]))

  def test_basic_query_not_in(self):
    """Filter by !~ operator."""
    title_pattern = "1"
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["title", "!~", title_pattern]),
        "Program",
    )

    self.assertEqual(programs["count"], 11)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertTrue(all(title_pattern not in program["title"]
                        for program in programs["values"]))

  def test_basic_query_lt(self):
    """Filter by < operator."""
    date = datetime(2015, 5, 18)
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["effective date", "<",
                                          date.strftime(DATE_FORMAT_REQUEST)]),
        "Program",
    )

    self.assertEqual(programs["count"], 9)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertTrue(
        all(datetime.strptime(program["start_date"],
                              DATE_FORMAT_RESPONSE) < date
            for program in programs["values"]),
    )

  def test_basic_query_gt(self):
    """Filter by > operator."""
    date = datetime(2015, 5, 18)
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["effective date", ">",
                                          date.strftime(DATE_FORMAT_REQUEST)]),
        "Program",
    )

    self.assertEqual(programs["count"], 13)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertTrue(
        all(datetime.strptime(program["start_date"],
                              DATE_FORMAT_RESPONSE) > date
            for program in programs["values"]),
    )

  def test_basic_query_text_search(self):
    """Filter by fulltext search."""
    text_pattern = "ea"
    data = self._make_query_dict("Regulation")
    data["filters"]["expression"] = {
        "op": {"name": "text_search"},
        "text": text_pattern,
    }
    regulations = self._get_first_result_set(data, "Regulation")

    self.assertEqual(regulations["count"], 21)
    self.assertEqual(len(regulations["values"]), regulations["count"])
    self.assertTrue(all((regulation["description"] and
                         text_pattern in regulation["description"]) or
                        (regulation["notes"] and
                         text_pattern in regulation.get("notes", ""))
                        for regulation in regulations["values"]))

  def test_basic_query_pagination(self):
    """Test basic query with pagination info."""
    from_, to_ = 1, 12
    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              expression=["title", "~", "Cat ipsum"],
                              order_by=[{"name": "title"}],
                              limit=[from_, to_]),
        "Program",
    )
    self.assertEqual(programs["count"], to_ - from_)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertEqual(programs["total"], 23)

  def test_basic_query_total(self):
    """The value of "total" doesn't depend on "limit" parameter."""
    programs_no_limit = self._get_first_result_set(
        self._make_query_dict("Program"),
        "Program",
    )
    self.assertEqual(programs_no_limit["count"], programs_no_limit["total"])

    from_, to_ = 3, 5
    programs_limit = self._get_first_result_set(
        self._make_query_dict("Program", limit=[from_, to_]),
        "Program",
    )
    self.assertEqual(programs_limit["count"], to_ - from_)

    self.assertEqual(programs_limit["total"], programs_no_limit["total"])

  def test_query_limit(self):
    """The limit parameter trims the result set."""
    def make_query_dict(limit=None):
      """A shortcut for making queries with different limits."""
      return self._make_query_dict("Program", order_by=[{"name": "title"}],
                                   limit=limit)

    def check_counts_and_values(programs, from_, to_, count=None):
      """Make a typical assertion set for count, total and values."""
      if count is None:
        count = to_ - from_
      self.assertEqual(programs["count"], count)
      self.assertEqual(programs["total"], programs_no_limit["total"])
      self.assertEqual(programs["values"],
                       programs_no_limit["values"][from_:to_])

    programs_no_limit = self._get_first_result_set(
        make_query_dict(),
        "Program",
    )

    self.assertEqual(programs_no_limit["count"], programs_no_limit["total"])

    programs_0_10 = self._get_first_result_set(
        make_query_dict(limit=[0, 10]),
        "Program",
    )

    check_counts_and_values(programs_0_10, from_=0, to_=10)

    programs_10_21 = self._get_first_result_set(
        make_query_dict(limit=[10, 21]),
        "Program",
    )

    check_counts_and_values(programs_10_21, from_=10, to_=21)

    programs_10_top = self._get_first_result_set(
        make_query_dict(limit=[10, programs_no_limit["total"] + 42]),
        "Program",
    )

    check_counts_and_values(programs_10_top, from_=10, to_=None,
                            count=programs_no_limit["total"] - 10)

    # check if a valid integer string representation gets casted
    programs_10_21_str = self._get_first_result_set(
        make_query_dict(limit=[10, "21"]),
        "Program",
    )
    programs_10_str_21 = self._get_first_result_set(
        make_query_dict(limit=["10", 21]),
        "Program",
    )

    self.assertDictEqual(programs_10_21_str, programs_10_21)
    self.assertDictEqual(programs_10_str_21, programs_10_21)

  def test_query_invalid_limit(self):
    """Invalid limit parameters are handled properly."""

    # invalid "from"
    self.assert400(self._post(
        self._make_query_dict("Program", limit=["invalid", 12]),
    ))

    # invalid "to"
    self.assert400(self._post(
        self._make_query_dict("Program", limit=[0, "invalid"]),
    ))

    # "from" >= "to"
    self.assert400(self._post(
        self._make_query_dict("Program", limit=[12, 0]),
    ))

    # negative "from"
    self.assert400(self._post(
        self._make_query_dict("Program", limit=[-2, 10]),
    ))

    # negative "to"
    self.assert400(self._post(
        self._make_query_dict("Program", limit=[2, -10]),
    ))

  def test_query_order_by(self):
    """Results get sorted by own field."""
    # assumes unique title

    def get_titles(programs):
      return [program["title"] for program in programs]

    programs_default = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "title"}]),
        "Program", "values",
    )
    titles_default = get_titles(programs_default)

    programs_asc = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "title", "desc": False}]),
        "Program", "values",
    )
    titles_asc = get_titles(programs_asc)

    programs_desc = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "title", "desc": True}]),
        "Program", "values",
    )
    titles_desc = get_titles(programs_desc)

    # the titles are sorted ascending with desc=False
    self.assertListEqual(titles_asc, sorted(titles_asc))
    # desc=False by default
    self.assertListEqual(titles_default, titles_asc)
    # the titles are sorted descending with desc=True
    self.assertListEqual(titles_desc, list(reversed(titles_asc)))

  def test_order_by_several_fields(self):
    """Results get sorted by two fields at once."""
    regulations = self._get_first_result_set(
        self._make_query_dict("Regulation",
                              order_by=[{"name": "notes", "desc": True},
                                        {"name": "title"}]),
        "Regulation", "values",
    )

    regulations_unsorted = self._get_first_result_set(
        self._make_query_dict("Regulation"),
        "Regulation", "values",
    )

    self.assertListEqual(
        regulations,
        sorted(sorted(regulations_unsorted,
                      key=itemgetter("title")),
               key=itemgetter("notes"),
               reverse=True),
    )

  def test_order_by_related_titled(self):
    """Results get sorted by title of related Titled object."""
    audits_title = self._get_first_result_set(
        self._make_query_dict("Audit",
                              order_by=[{"name": "program"}, {"name": "id"}]),
        "Audit", "values",
    )

    audits_unsorted = self._get_first_result_set(
        self._make_query_dict("Audit"),
        "Audit", "values",
    )

    # get titles from programs to check ordering
    programs = self._get_first_result_set(
        self._make_query_dict("Program"),
        "Program", "values",
    )
    program_id_title = {program["id"]: program["title"]
                        for program in programs}

    self.assertListEqual(
        audits_title,
        sorted(sorted(audits_unsorted, key=itemgetter("id")),
               key=lambda a: program_id_title[a["program"]["id"]]),
    )

  def test_order_by_related_person(self):
    """Results get sorted by name or email of related Person object."""
    clauses_person = self._get_first_result_set(
        self._make_query_dict("Clause",
                              order_by=[{"name": "contact"}, {"name": "id"}]),
        "Clause", "values",
    )

    clauses_unsorted = self._get_first_result_set(
        self._make_query_dict("Clause"),
        "Clause", "values",
    )

    # get names and emails from people to check ordering
    people = self._get_first_result_set(
        self._make_query_dict("Person"),
        "Person", "values",
    )
    person_id_name = {person["id"]: (person["name"], person["email"])
                      for person in people}

    self.assertListEqual(
        clauses_person,
        sorted(sorted(clauses_unsorted, key=itemgetter("id")),
               key=lambda c: person_id_name[c["contact"]["id"]]),
    )

  def test_query_order_by_owners(self):
    """Results get sorted by name or email of the (first) owner."""
    # TODO: the test data set lacks objects with several owners
    policies_owner = self._get_first_result_set(
        self._make_query_dict("Policy",
                              order_by=[{"name": "owners"}, {"name": "id"}]),
        "Policy", "values",
    )
    policies_unsorted = self._get_first_result_set(
        self._make_query_dict("Policy"),
        "Policy", "values",
    )
    people = self._get_first_result_set(
        self._make_query_dict("Person"),
        "Person", "values",
    )
    person_id_name = {person["id"]: (person["name"], person["email"])
                      for person in people}
    policy_id_owner = {policy["id"]: person_id_name[policy["owners"][0]["id"]]
                       for policy in policies_unsorted}

    self.assertListEqual(
        policies_owner,
        sorted(sorted(policies_unsorted, key=itemgetter("id")),
               key=lambda p: policy_id_owner[p["id"]]),
    )

  def test_query_count(self):
    """The value of "count" is same for "values" and "count" queries."""
    programs_values = self._get_first_result_set(
        self._make_query_dict("Program", type_="values"),
        "Program",
    )
    programs_count = self._get_first_result_set(
        self._make_query_dict("Program", type_="count"),
        "Program",
    )

    self.assertEqual(programs_values["count"], programs_count["count"])

  def test_query_ids(self):
    """The ids are the same for "values" and "ids" queries."""
    programs_values = self._get_first_result_set(
        self._make_query_dict("Program", type_="values"),
        "Program",
    )
    programs_ids = self._get_first_result_set(
        self._make_query_dict("Program", type_="ids"),
        "Program",
    )

    self.assertEqual(
        set(obj.get("id") for obj in programs_values["values"]),
        set(programs_ids["ids"]),
    )

  @SkipTest
  def test_self_link(self):
    # It would be good if the api accepted get requests and we could add the
    # query into a get parameter, then each request would also get a self link
    # that could be tested to see that it truly returns what the original
    # request was.
    # In the end, instead of returning mapped object stubs like we do now, we'd
    # just return a self link for fetching those objects.
    pass

  def test_multiple_queries(self):
    """Multiple queries POST is identical to multiple single-query POSTs."""
    data_list = [
        self._make_query_dict("Program",
                              order_by=[{"name": "title"}],
                              limit=[1, 12],
                              expression=["title", "~", "Cat ipsum"]),
        self._make_query_dict("Program",
                              type_="values"),
        self._make_query_dict("Program",
                              type_="count"),
        self._make_query_dict("Program",
                              type_="ids"),
        self._make_query_dict("Program",
                              type_="ids",
                              expression=["title", "=", "Cat ipsum 1"]),
        self._make_query_dict("Program",
                              expression=["title", "~", "1"]),
        self._make_query_dict("Program",
                              expression=["title", "!=", "Cat ipsum 1"]),
        self._make_query_dict("Program",
                              expression=["title", "!~", "1"]),
        self._make_query_dict("Program",
                              expression=["effective date", "<",
                                          "05/18/2015"]),
        self._make_query_dict("Program",
                              expression=["effective date", ">",
                                          "05/18/2015"]),
        {
            "object_name": "Regulation",
            "fields": ["description", "notes"],
            "filters": {
                "expression": {
                    "op": {"name": "text_search"},
                    "text": "ea",
                },
            },
        },
    ]

    response_multiple_posts = [json.loads(self._post(data).data)[0]
                               for data in data_list]
    response_single_post = json.loads(self._post(data_list).data)

    self.assertEqual(response_multiple_posts, response_single_post)


class TestQueryWithCA(BaseQueryAPITestCase):
  """Test query API with custom attributes."""

  def setUp(self):
    """Set up test cases for all tests."""
    TestCase.clear_data()
    self._generate_cad()
    self._import_file("sorting_with_ca_setup.csv")
    self.client.get("/login")

  @staticmethod
  def _generate_cad():
    """Generate custom attribute definitions."""
    factories.CustomAttributeDefinitionFactory(
        title="CA dropdown",
        definition_type="program",
        multi_choice_options="one,two,three,four,five",
    )
    factories.CustomAttributeDefinitionFactory(
        title="CA text",
        definition_type="program",
    )

  @staticmethod
  def _flatten_cav(data):
    """Unpack CAVs and put them in data as object attributes."""
    cad_names = dict(db.session.query(CAD.id, CAD.title))
    for entry in data:
      for cav in entry.get("custom_attribute_values", []):
        entry[cad_names[cav["custom_attribute_id"]]] = cav["attribute_value"]
    return data

  def _get_first_result_set(self, *args, **kwargs):
    """Call this method from super and flatten CAVs additionally."""
    return self._flatten_cav(
        super(TestQueryWithCA, self)._get_first_result_set(*args, **kwargs),
    )

  def test_single_ca_sorting(self):
    """Results get sorted by single custom attribute field."""

    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "title"}]),
        "Program", "values",
    )

    keys = [program["title"] for program in programs]
    self.assertEqual(keys, sorted(keys))

    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "CA text"}]),
        "Program", "values",
    )

    keys = [program["CA text"] for program in programs]
    self.assertEqual(keys, sorted(keys))

  def test_mixed_ca_sorting(self):
    """Test sorting by multiple fields with CAs."""

    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "CA text"},
                                        {"name": "title"}]),
        "Program", "values",
    )

    keys = [(program["CA text"], program["title"]) for program in programs]
    self.assertEqual(keys, sorted(keys))

    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "title"},
                                        {"name": "CA text"}]),
        "Program", "values",
    )

    keys = [(program["title"], program["CA text"]) for program in programs]
    self.assertEqual(keys, sorted(keys))

  def test_multiple_ca_sorting(self):
    """Test sorting by multiple CA fields"""

    programs = self._get_first_result_set(
        self._make_query_dict("Program",
                              order_by=[{"name": "CA text"},
                                        {"name": "CA dropdown"}]),
        "Program", "values",
    )

    keys = [(prog["CA text"], prog["CA dropdown"]) for prog in programs]
    self.assertEqual(keys, sorted(keys))


class TestQueryWithUnicode(BaseQueryAPITestCase):
  """Test query API with unicode values."""

  def setUp(self):
    """Set up test cases for all tests."""
    TestCase.clear_data()
    self._generate_cad()
    self._import_file("querying_with_unicode.csv")
    self.client.get("/login")

  @staticmethod
  def _generate_cad():
    """Generate custom attribute definitions."""
    factories.CustomAttributeDefinitionFactory(
        title=u"CA список",
        definition_type="program",
        multi_choice_options=u"один,два,три,четыре,пять",
    )
    factories.CustomAttributeDefinitionFactory(
        title=u"CA текст",
        definition_type="program",
    )

  @staticmethod
  def _flatten_cav(data):
    """Unpack CAVs and put them in data as object attributes."""
    cad_names = dict(db.session.query(CAD.id, CAD.title))
    for entry in data:
      for cav in entry.get("custom_attribute_values", []):
        entry[cad_names[cav["custom_attribute_id"]]] = cav["attribute_value"]
    return data

  def test_query(self):
    """Test query by unicode value."""
    title = u"программа A"
    programs = self._get_first_result_set(
        self._make_query_dict("Program", expression=["title", "=", title]),
        "Program",
    )

    self.assertEqual(programs["count"], 1)
    self.assertEqual(len(programs["values"]), programs["count"])
    self.assertEqual(programs["values"][0]["title"], title)

  def test_sorting_by_ca(self):
    """Test sorting by CA fields with unicode names."""
    programs = self._flatten_cav(
        self._get_first_result_set(
            self._make_query_dict("Program",
                                  order_by=[{"name": u"CA текст"},
                                            {"name": u"CA список"}]),
            "Program", "values",
        )
    )

    keys = [(prog[u"CA текст"], prog[u"CA список"]) for prog in programs]
    self.assertEqual(keys, sorted(keys))
