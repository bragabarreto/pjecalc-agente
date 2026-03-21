/*
 * Objeto principal de assinatura via REST.
 */
var AssinadorJT = (function() {

  var URL_BASE          = 'https://127.0.0.1:9000';
  var URL_ASSINAR_TEXTO = URL_BASE + '/assinarTexto';
  var URL_ASSINAR_HASH  = URL_BASE + '/assinarHash';
  var URL_ASSINAR_P7S   = URL_BASE + '/assinarP7s';  

  // Função de erro padrão
  var erroAssinaturaCallback = function(codigo, mensagemHttp, response) {
	alert(response.responseText);
    console.log(codigo, '(', mensagemHttp, '): ', response.responseText);
  }
  
  /**
   * Bug no JSON.stringify
   * https://github.com/mozilla/jschannel/pull/18
   */
  var stringify = function (value) {
	  var _json_stringify = JSON.stringify;
	  var _array_tojson = Array.prototype.toJSON;
      delete Array.prototype.toJSON;
      var r=_json_stringify(value);
      Array.prototype.toJSON = _array_tojson;
      return r;
  };

  /**
   * Comando de assinatura (desenvolvedor fornece callback de erro).
   * 
   * @param url
   * 			endereço para postagem
   * @param parametro
   * 			parâmetro(s) para submeter; pode ser em forma de Array ([]) ou String
   * @param sucessoCallback
   * 			função a ser chamada em caso de sucesso na chamada da URL
   * @param erroCallback
   * 			função a ser chamada em caso de erro na chamada da URL
   */ 
  var assinar = function(url, parametros, sucessoCallback, erroCallback) {
    Twix.ajax({
      url:     url, 
      type:    'POST',
      data:    stringify(parametros),
      success: sucessoCallback,
      error:   erroCallback
    });
  }

  return {   
    assinarTexto: function(parametros, sucesso, erro) {
      assinar(URL_ASSINAR_TEXTO, parametros, sucesso, erro || erroAssinaturaCallback);
    },
    assinarHash: function(parametros, sucesso, erro) {
      assinar(URL_ASSINAR_HASH, parametros, sucesso, erro || erroAssinaturaCallback);
    },
    assinarP7s: function(parametros, sucesso, erro) {
      assinar(URL_ASSINAR_P7S, parametros, sucesso, erro || erroAssinaturaCallback);
    }
  }
})();

/*
 * Twix: Twix is a lightweight JavaScript library for making AJAX requests in places where jQuery won't go.
 * https://github.com/neilco/twix
 */
var Twix=function(){function t(){}return t.ajax=function(t){t=t||{url:""},t.type=t.type.toUpperCase()||"GET",t.headers=t.headers||{},t.timeout=parseInt(t.timeout)||0,t.success=t.success||function(){},t.error=t.error||function(){},t.async="undefined"==typeof t.async?!0:t.async;var e=new XMLHttpRequest;t.timeout>0&&(e.timeout=t.timeout,e.ontimeout=function(){t.error("timeout","timeout",e)}),e.open(t.type,t.url,t.async);for(var s in t.headers)t.headers.hasOwnProperty(s)&&e.setRequestHeader(s,t.headers[s]);return e.send(t.data),e.onreadystatechange=function(){if(4==this.readyState&&200==this.status){var e=this.responseText;this.getResponseHeader("Content-Type").match(/json/)&&(e=JSON.parse(this.responseText)),t.success(e,this.statusText,this)}else 4==this.readyState&&t.error(this.status,this.statusText,this)},0==t.async&&(4==e.readyState&&200==e.status?t.success(e.responseText,e):4==e.readyState&&t.error(e.status,e.statusText,e)),e},t.get=function(e,s,r){return"function"==typeof s&&(r=s,s=void 0),t.ajax({url:e,data:s,success:r})},t.post=function(e,s,r){return"function"==typeof s&&(r=s,s=void 0),t.ajax({url:e,type:"POST",data:s,success:r})},t}();__=Twix;