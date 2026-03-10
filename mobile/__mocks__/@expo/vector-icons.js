const React = require('react');
const { View, Text } = require('react-native');
const Ionicons = ({ name, size, color }) =>
  React.createElement(Text, { testID: `icon-${name}`, style: { color } }, name);
module.exports = { Ionicons };
