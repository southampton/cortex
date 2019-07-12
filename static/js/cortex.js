function enableMenuTooltip(selector){
	$(selector).tooltip(
	{
		trigger: 'hover',
		placement: 'right',
		container: 'body'
	});
}
function show_popover(target) {
	var popover = $(target);
	selected_point.h = popover.height();
	var xPos = selected_point.x + 15;
	var yPos = selected_point.y - (selected_point.h / 2) - 12;
	var maxRight = $( window ).width() - popover.width();
	var maxDown = $( window ).height() - popover.height();
	if (xPos > maxRight) {
	xPos = maxRight;
	}
	if (yPos > maxDown) {
	yPos = maxDown;
	}
	$('.popover').css('left', xPos +'px');
	$('.popover').css('top',  yPos +'px');
	$('.popover').popover('show');
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
			template: '<div class="popover" role="tooltip"><div class="arrow"></div><div class="popover-body"></div></div>',
			boundary: 'viewport',
		}).on('mouseenter', function(event) {
			var button = this;
			$(this).popover('show');
			$('.popover').on('mouseleave', function () {
				$(button).popover('hide');
			});
		}).on('mouseleave', function () {
			var button = this;
			setTimeout(function () {
				if (!$(".popover:hover").length) {
					$(button).popover("hide");
				}
			}, 62);
		})
		//click(togglePopover).blur(hidePopover);
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
		$(this).tooltip('dispose');
	});

	$('.enable-menu-popover').on('hide.bs.popover', function()
	{
		enableMenuTooltip(this);
	});

	$("#search").on('shown.bs.modal', function()
	{
		$("#searchinput").focus();
	});

	$("#puppet-search").on('shown.bs.modal', function()
	{
		$("#puppetsearchinput").focus();
	});

	/* Searching for systems */
	Mousetrap.bind('alt+s', function(e)
	{
		$("#search").modal('show');
		$("#searchinput").focus();
		e.preventDefault();
	});


});


