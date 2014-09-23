define(['moment', 'underscore'], function (moment, _) {
    'use strict';
    var utils = {
        /**
         * Returns the attributes of a node.
         *
         * @param nodeAttributes Attributes of the node.
         * @param startsWithAndStrip Filters only attributes that start with
         *   this string and strips it off the attribute.
         * @param blackList Exclude attributes in this array of strings.
         * @returns Hash of found attributes.
         */
        getNodeProperties: function (nodeAttributes, startsWithAndStrip, blackList) {
            var properties = {};

            // fill in defaults
            startsWithAndStrip = startsWithAndStrip || '';
            blackList = blackList || [];

            _(_(nodeAttributes.length).range()).each(function (i) {
                var nodeName = nodeAttributes.item(i).nodeName,
                    strippedName;
                // filter the attributes to just the ones that start with our
                // selection and aren't in our blacklist
                if (nodeName.indexOf(startsWithAndStrip) === 0 && !_(blackList).contains(nodeName)) {
                    // remove the
                    strippedName = nodeName.replace(startsWithAndStrip, '');
                    properties[strippedName] =
                        nodeAttributes.item(i).value;
                }
            });
            return properties;
        },

        /**
         * Takes a standard string date and returns a formatted date.
         * @param {string} date (ex. 2014-01-31)
         * @returns {string} Returns a formatted date (ex. January 31, 2014)
         */
        formatDate: function (date) {
            moment.locale(window.language);
            return moment(date).format('LL');
        },

        /**
         * Return the decimal separator for the current locale.
         * @returns {string}
         */
        decimalSeparator: function () {
            if (!window.decimalSeparator){
                window.decimalSeparator = this.localizeNumber(1.1).substring(1, 2);
            }

            return window.decimalSeparator;
        },

        /**
         * Format the given number for the current locale
         * @param value {number}
         * @returns {string|null}
         */
        localizeNumber: function (value) {
            if (value) {
                return value.toLocaleString(window.language);
            }

            return null;
        },

        /**
         * Format the given value as a percentage to be displayed to the end user.
         * @param value {number}
         * @returns {string}
         */
        formatDisplayPercentage: function (value) {
            var display = '< 1%';
            if (value >= 0.01) {
                var fixed = (value * 100).toFixed(1);
                fixed = fixed.replace('.', this.decimalSeparator());
                display = fixed + '%';
            }

            return display;
        }
    };

    return utils;
});
