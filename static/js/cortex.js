/* Tooltips and Popovers */
$(document).ready(function ()
{
	$("[rel=tooltip]").tooltip(); /* TODO: remove this monstrosity when sure its not in use anymore */
	$(".enable-tooltip").tooltip();
	$(".enable-popover").popover();

	$('.enable-menu-popover').each(function()
	{
		$(this).popover(
		{
			trigger: 'focus',
			placement: 'right',
			html: true,
			container: 'body',
			content: $("#" + $(this).data("mpop")).html(),
			template: '<div class="popover" role="tooltip"><div class="arrow"></div><div class="popover-content popover-content-nopad"></div></div>'
		});
	});

	$('.mobilepop').each(function()
	{
		$(this).popover(
		{
			trigger: 'focus',
			placement: 'bottom',
			html: true,
			container: 'body',
			content: $("#" + $(this).data("mpop")).html(),
			template: '<div class="popover" role="tooltip"><div class="arrow"></div><div class="popover-content popover-content-nopad"></div></div>'
		});
	});

	$('.enable-menu-popover').click(function()
	{
		$(this).tooltip('hide');
	});

	$("#search").on('shown.bs.modal', function()
	{
		$("#searchinput").focus();
	});

});


