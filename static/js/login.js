/* BARGATE LOGIN JAVASCRIPT */

window.onload = function()
{
  var text_input = document.getElementById ('loginUsername');
  text_input.focus();
  text_input.select();
}

/* Tooltip */
$(document).ready(function ()
{
  $('[data-toggle="popover"]').popover()
});
