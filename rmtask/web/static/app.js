document.addEventListener('submit', function (e) {
  var form = e.target.closest('form[data-confirm]');
  if (form && !window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
});
