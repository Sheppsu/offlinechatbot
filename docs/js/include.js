$(function () {
  var includes = $('[data-include]')
  $.each(includes, function (i, element) {
    const m = $(this)
    var file = 'templates/' + $(this).data('include') + '.html'
    $("<div/>").load(file, function() {
        m.append($(this).children())
    })
  })
})