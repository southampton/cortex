function enableMenuTooltip(selector){
	$(selector).tooltip(
	{
		trigger: 'hover',
		placement: 'right',
		container: 'body'
	});
}
	
/* Tooltips and Popovers */
$(document).ready(function ()
{
	//$("[rel=tooltip]").tooltip(); /* TODO: remove this monstrosity when sure its not in use anymore */
	enableMenuTooltip('.enable-tooltip');	
	$(".enable-popover").popover();
	
	var togglePopover = function () {
		$(this).popover('toggle');
	};
	var hidePopover = function () {
		$(this).popover('hide');
	};
	$('.enable-menu-popover').each(function()
	{
		$(this).popover(
		{
			trigger: 'manual',
			placement: 'right',
			html: true,
			container: 'body',
			content: $("#" + $(this).data("mpop")).html(),
			template: '<div class="popover" role="tooltip"><div class="arrow"></div><div class="popover-content popover-content-nopad"></div></div>'
		}).click(togglePopover).blur(hidePopover);
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

	$('.enable-menu-popover').on('show.bs.popover', function()
	{
		$(this).tooltip('destroy');
	});

	$('.enable-menu-popover').on('hide.bs.popover', function()
	{
		enableMenuTooltip(this);
	});


	$("#search").on('shown.bs.modal', function()
	{
		$("#searchinput").focus();
	});
});


