export function csrfHeaders () {
  const token = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith('csrftoken='))
  return token ? { 'X-CSRFToken': decodeURIComponent(token.slice('csrftoken='.length)) } : {}
}
