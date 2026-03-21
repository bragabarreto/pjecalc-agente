var efeito =  function() {
	removeEfeito();
	jQuery('.ff-resumo li')
		.live('mouseenter', function() {
			jQuery(this).stop().animate(
				{backgroundColor: '#F9F9F9'},
				{duration: 'fast',
				easing: 'swing'
			});
		})
		.live('mouseleave', function() {
			jQuery(this).stop().animate(
				{backgroundColor: '#FFF'},
				{duration: 'normal',
				easing: 'swing'
			});
		});
};

var removeEfeito = function() {
	jQuery('.ff-resumo li').die('mouseenter').die('mouseleave');
}

var doNormalView = function(){
	
	jQuery('.ff-control-expand a').attr('title', 'abrir');
	jQuery('.ff-control-expand a').attr('alt', 'abrir');

	$container = jQuery('#barra-resumo');

	jQuery('.ff-conteudo-expand').animate({height: 0});
    jQuery(".ff-titulo .titulo-proj", $container).text("Menu Lateral").removeClass('livefeed-titulo').addClass('atualizacoes-titulo');
    jQuery(".ff-titulo .busca-titulo", $container).text("Buscar Projeto").removeClass('livefeed-titulo').addClass('atualizacoes-titulo');
//	$container.removeClass("expanded-view").addClass("normal-view");
	jQuery('.ff-control-expand a').removeClass("menos");
};

var doExpandView = function(){
	
	novosItens = [];
	
	$container = jQuery('#barra-resumo');
	$ffct = jQuery('.ff-conteudo-expand');
	
	jQuery('.ff-control-expand a').attr('title', 'fechar');
	jQuery('.ff-control-expand a').attr('alt', 'fechar');
	
//	$(".ff-materia .titulo-proj", $container).text('Resumo do Projeto: ').css('font-size','14px');
	$ffct.show().animate({height: 52}, function(){
		efeito();
	});
	//$(".ff-titulo .titulo-proj", $container).text("Menu Lateral").removeClass('atualizacoes-titulo').addClass('livefeed-titulo');
	//$container.removeClass("normal-view").addClass("expanded-view");
	jQuery('.ff-control-expand a').addClass('menos');
};

var toogleExpand = function(){
	jQuery('#barra-resumo').hasClass("expanded-view") ? doNormalView() : doExpandView();
	return false;
};

var swapView = function( e ){
	
	$container = jQuery('#barra-resumo');
	$ffct = jQuery('.ff-conteudo-expand');
	
	if ($container.hasClass("compact-view") || $container.hasClass("update-view")){
		//setCookie("livefeed-view", "normal-view", 3);
	
		if ($container.hasClass("update-view")) jQuery('.ff-control-update').hide();

		jQuery('.ff-control-view a').attr('title', 'esconder');
		$container.removeClass().addClass("normal-view");
		//timer.start();
	} else {
		//setCookie("livefeed-view", "compact-view", 3);

		jQuery('.ff-control-view a').attr('title', 'exibir');
		$container.removeClass().addClass("compact-view");
		$ffct.css('height', 0);
		doNormalView();
		//timer.pause();
	}
	jQuery("#tiptip_holder").fadeOut( 200 ); //forcando o kill do tooltip
	jQuery('.ff-control-expand a').attr('title', 'abrir');
	
	//connectToolTip($('.ff-control-view a'));
	return false;
};
