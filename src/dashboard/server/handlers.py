from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import *
from mozautoeslib import ESLib
import ConfigParser
import csv
import dateutil.parser
import re
import templeton
import templeton.handlers
import web

try:
  import json
except:
  import simplejson as json

config = ConfigParser.ConfigParser()
config.read("settings.cfg")
ES_SERVER = config.get("database", "ES_SERVER")
eslib = ESLib(ES_SERVER, config.get("database", "INDEX"), config.get("database", "TYPE"))

# "/api/" is automatically prepended to each of these
urls = (
 '/perfdata/?',"PerfdataHandler",
 '/xbrowserstartup/?', "CrossBrowserStartupHandler"
)

class PerfdataHandler():
    @templeton.handlers.json_response
    def GET(self):
        params,body = templeton.handlers.get_request_parms()

        queryparams = defaultdict()

        #No params supplied -- query everything
        if not params:
            queryparams["test"] = "*"

        #Params supplied, query by them
        for arg in params:
            #Treat startdate and enddate uniquely (build a daterange for the query)
            if arg == "startdate" or arg == "enddate":
                try:
                    queryparams["date"].append(str(params[arg][0]))
                except:
                    queryparams["date"] = []
                    queryparams["date"].append(str(params[arg][0]))
            else:
                queryparams[arg] = params[arg][0]

        #Query based on params supplied, return json
        result = eslib.query(queryparams)
        return result

class CrossBrowserStartupHandler():
    @templeton.handlers.json_response
    def GET(self):
        params,body = templeton.handlers.get_request_parms()
        data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda:defaultdict(list))))

        es = ESLib('elasticsearch1.metrics.sjc1.mozilla.com:9200','xbrowserstartup', 'perfdata')

        # Create a version suitable for graphing from this:
        # {"x-series":["date1","date2",...."enddate"],
        #  "series":[{"name":"<phone1>-<browser1>",
        #             "data":[<date_point>, "<date_point>",..."<date_point>"]},
        #            {"name":"<phone1>-<browser2>",
        #             "data":[<date_point>, "<date_point>",..."<date_point>"]},
        #            ...
        #            {"name":"<phonem>-<browsern>",
        #             "data":[<date_point>, "<date_point>",..."<date_point>"]}]}
        testname = params["test"][0] + "-" + params["style"][0] + "-startup"
        xseries = self.get_date_range(params["date"][0])
        series = []

        # Dates in format YYYY-mm-dd
        for date in xseries:
            results = es.query({'date': date})

            for result in results:
                perfdata = result['perfdata'][0]
                data[result['revision']][perfdata['phone']][perfdata['browser']][perfdata['type']].append(perfdata['result'])

            # Get averages for each testrun for each browser from this day
            # Make a point from (date, avg of testrun on phone-browser, phone-browser)
            for rev in data:
                for phone in data[rev]:
                    for browser in data[rev][phone]:
                        phone_browser = phone + "-" + browser
                        # If our phone browser combo not in the series add it.
                        # If it is in the list return the index.
                        # Either way we get the index of the phone_browser
                        # combo in the list.
                        idx = self.ensure_in_series(phone_browser, series)

                        # Average our test scores for this phone-browser in
                        # the given revision
                        print "------------"
                        print "REV: %s" % rev
                        print "PHONE: %s" % phone
                        print "BROWSER: %s" % browser
                        print "TESTARRAY %s" % data[rev][phone][browser][testname]
                        avg = self.average(data[rev][phone][browser][testname])
                        # Add our point to the series data
                        series[idx]["data"].append([date, avg, phone_browser])

        retval = {"xseries": xseries, "series": series}
        #print retval
        return retval

    def ensure_in_series(self, phone_browser, series):
        for i in range(len(series)):
            if series[i]['name'] == phone_browser:
                return i
        # If we don't find it, add it
        series.append({"name":phone_browser, "data":[]})
        return series.index({"name":phone_browser, "data":[]})

    def average(self, ary):
        if len(ary) == 0:
            return 0

        t = 0
        for i in ary:
            t = t + i
        return t/len(ary)

    def get_date_range(self, val):
        now = date.today()
        if val == "1w":
            old = now - timedelta(weeks=1)
        elif val == "2w":
            old = now - timedelta(weeks=2)
        elif val == "1m":
            old = now - timedelta(weeks=4)
        else:
            # Go back maximum of six months
            old = now - timedelta(weeks=24)
        dates = []

        while old <= now:
            dates.append("%s-%s-%s"% (old.year, old.month, old.day))
            old = old + timedelta(days=1)
        return dates
