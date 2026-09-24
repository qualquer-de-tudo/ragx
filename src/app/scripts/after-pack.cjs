// Hook afterPack do electron-builder: grava ícone e metadados no .exe.
//
// O electron-builder faria isso sozinho via rcedit, mas o dele vem do pacote
// winCodeSign, cujo download falha em Windows sem "Developer Mode" (por isso
// signAndEditExecutable: false em electron-builder.yml). O rcedit do npm traz
// o binário junto e não tem esse problema.
const path = require('node:path')
const rcedit = require('rcedit')

exports.default = async function afterPack(context) {
  if (context.electronPlatformName !== 'win32') return
  const info = context.packager.appInfo
  const exe = path.join(context.appOutDir, `${info.productFilename}.exe`)
  await rcedit(exe, {
    icon: path.join(context.packager.projectDir, 'build', 'icon.ico'),
    'file-version': info.version,
    'product-version': info.version,
    'version-string': {
      ProductName: info.productName,
      FileDescription: info.productName,
      OriginalFilename: `${info.productFilename}.exe`,
    },
  })
}
