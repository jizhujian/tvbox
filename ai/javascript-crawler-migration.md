# JavaScript 爬蟲舊 API 遷移

本文件適用於本次 QuickJS 爬蟲 API 清理後的原始碼，尚未對應已發布的模組版本；實際使用需搭配包含此異動的 QuickJS 模組與相容 App；wrapper Java 與 JNI 必須來自相同來源，舊 JNI 不能搭配新增的物件綁定 API。建置方式見[執行環境模組](runtime-modules.md)。

清理依據是重複入口、隱含行為與舊協定的維護成本。方法較舊、名稱較短或標準 API 能完成類似工作，都不足以單獨構成移除理由。

## AI 遷移順序

先讀[替換清單](#替換清單)、[爬蟲入口](#爬蟲入口)、[完整 ID 集合](#完整-id-集合)與[驗證](#驗證)，再依來源使用的功能閱讀其餘段落。本文件是修改規則，不代表所有使用端都已完成遷移。

1. 從配置的 sites／lives 追查本地及遠端入口、必要 helper、ext 格式與配套 App／wrapper／runtime；取不到的遠端原始碼列為未驗證。區分 QuickJS 爬蟲與 Node.js 工具，不把 require、process、Buffer 或 DOM 當成宿主能力。
2. 保存既有分類、篩選、搜尋、列表 ID、每集播放值與登入流程，確認請求的正文、編碼、Cookie、簽名及錯誤處理。
3. 改為 default Spider 子類別與公開 catvod API，同步修改 helper 的 imports 及 vendor 路徑；不匯入 catvod:host 或自行重建 ctx.bind 橋接。
4. 沿呼叫鏈處理 Promise，核對完整 ids／vipFlags、搜尋頁碼與分類 extend。不能只加 async 或只改方法名稱；詳情只處理 ids[0] 仍未完成遷移。
5. 依語意選 net.json／req、batch／map、Local／TTL；代理的 URL 產生端、接收參數與回傳格式一起修改，不更動來源的簽名、登入與字元編碼規則。
6. 核對 Session、reader、WebSocket、彈幕停止回呼及 destroy 的資源釋放，再依驗證表逐項回報；Node.js 語法或單筆成功不代表全部入口與 Android 已通過。

共用欄位與可選功能見 CatVodSpider 的 `docs/development.md` 與 QuickJS Demo。核對實作時，TV repo 的 `quickjs/src/main/assets/js/lib/catvod.js` 定義公開 SDK，`quickjs/src/main/assets/js/lib/net.js` 定義網路合約，`quickjs/src/main/java/com/fongmi/quickjs/crawler/Spider.java` 負責入口轉接；爬蟲仍只使用公開 API。

## 替換清單

| 舊寫法 | 現行寫法 | 移除原因與差異 |
| --- | --- | --- |
| 全域 `req/http/ws/connect` | `this.net.req/ws/connect` 或明確匯入 `net` | 網路能力由 Spider 資源及模組提供 |
| 全域 `session/sleep/cached/clearCache` | `this.net.session/sleep/cached/clearCache` | 移除與 net 重複的入口 |
| 全域 `getCookie/setCookie/getUserAgent` | `this.net.getCookie/setCookie/getUserAgent` | 根網路仍使用 App 的登入資訊與 UA；子 session 保持隔離 |
| 同步 `net.req()`、`net.http()` | `await this.net.req(url, options)` | HTTP 統一回傳 Promise；子 session 與 batch 同樣使用 req，不保留 http 別名 |
| `http/ws(url, {async, complete})` | `await this.net.req/ws(url, options)` | 一次請求只使用 Promise，不以 options 改變交付方式 |
| `evalJs(source, options)` | `await this.js.eval(source, options)` | 保留受管理的腳本執行 |
| `global/window/self` 別名 | `globalThis` | 使用標準全域物件名稱；QuickJS 爬蟲並未因此提供 DOM |
| `__jsEvalReturn()`、`__JS_SPIDER__`、default 物件／factory | `export default class extends Spider` | 統一為與 Java／Python 相近的類別入口 |
| `dialog({...options, onAction})`、`dialog.show(options, callback)` | `await this.dialog(options, callback)` | callback 是選填第二個參數，options 只放資料 |
| `js2Proxy()`、`proxy2()` 與 `from=catvod` 協定 | `this.proxyUrl(params)` 與 `proxy(params)` | URL、接收參數與回傳陣列一起修改，不再使用 Res |
| `getProxyUrl(params)`、`getProxy(local)` | `this.proxyUrl(params, local)` | 字串鍵值參數；local 預設 true，false 使用區域網路 IP，沒有舊別名 |
| `getDanmakuUrl(id)` | `this.danmakuUrl(id)` | 由 App 加入站點識別，沒有舊別名 |

`net.req/ws` 固定回傳 Promise；舊 async／complete 欄位不影響交付方式，也不會觸發回呼，遷移時刪除。可省略的 options 接受 null，視為空物件。`net.connect(url, options, listener)` 的 listener 用於持續 WebSocket 事件。

公開 API 從 `catvod` 模組匯入。`hostReq`、`hostHttp` 等橋接不再註冊為全域函式；底層函式綁定在原生物件，由內部 `catvod:host` 模組持有。爬蟲派送與 Dialog callback 也由宿主持有引用，不公開 spider／dialogActions 全域物件。session 路由欄位 netId 仍由宿主管理。

## 網路請求

JS 使用 `await net.req`，不再提供同步 HTTP。方法名稱與 Java／Python 對齊；JS 的 Promise 交付方式仍保留語言本身的非同步模型。時間單位為毫秒。

```javascript
import {net} from "catvod";

const response = await net.req(url, {
    params: {keyword: key, page: pg},
    headers,
    timeout: 5000
});
if (response.error) throw new Error(response.error);
if (response.code < 200 || response.code >= 300) throw new Error(`HTTP ${response.code}`);
const text = response.content;
```

呼叫端必須等待 Promise，不能直接讀取 `net.req(...).content`。HTTP 非 2xx 仍保留回應，網路失敗則帶有 error；不要把登入頁或錯誤正文當成成功列表。

只需要 JSON 時使用 `const data = await net.json(url, options)`；網路失敗、HTTP 非 2xx 或無效 JSON 會拋出例外。一般請求預設回傳文字，`buffer: 3` 回傳 ArrayBuffer，可交給 Uint8Array、TextDecoder 或代理。

| buffer | content |
| --- | --- |
| `0` 或省略 | 文字，依回應編碼解碼 |
| `1` | 有號 byte 陣列，值為 -128～127 |
| `2` | Base64 字串 |
| `3` | ArrayBuffer；Python 對應 bytes |

buffer 只接受 0～3 的整數，net.json 使用文字模式。一般二進位用 3；若把 buffer: 1 的結果用於 body／proxy，先將每個值以 `value & 255` 轉成 0～255。`buffer: 2` 仍可使用，與已移除的 proxy 第五格旗標不同。

需要區分 403 的會員限制、保留大整數 ID，或正文還需解密時，保留 req 與來源自己的解析流程。req 後使用 JSON.parse 本身不是過時寫法，不把 HTTP 錯誤或解析失敗改成成功空列表，也不把已登入流程改為訪客請求。

| 請求情況 | 現行寫法與注意事項 |
| --- | --- |
| URL query | options.params，保留來源既有編碼及同名參數，不手動重複編碼 |
| 表單 | `{method: "POST", postType: "form", data: fields}`；postType 預設 json，不能只搬 data |
| JSON | `{method: "POST", postType: "json", data: value}`；data 與 body 擇一 |
| 原始正文 | `{method: "POST", body: text, headers: {"Content-Type": mime}}`；二進位 body 用 0～255 整數陣列 |
| 二進位回應 | `await net.req(url, {buffer: 3})`，檢查 error／code 後使用 content |
| 持續 WebSocket | `net.connect(url, options, listener)`；listener 處理事件，不是舊 complete callback |
| 每筆有解析或簽名 | `await net.map(items, mapper, 4)`；mapper 接收 item、index，保留輸入順序 |
| 固定 HTTP 批次 | `await net.batch(requests, 4)`；每筆是 `{url, options}`，逐一檢查結果 |

GET／HEAD 不傳正文。buffer 只控制回應，不會把 JSON data 中的 Uint8Array 變成原始二進位正文。共用 net 沒有逐次請求指定代理的 options；若來源另有此需求，保留其能力並列明缺口，不傳入未支援的 proxy／proxies 欄位當成已完成。

根網路的 Cookie API 仍對應 App 登入資訊。需要獨立 Cookie 與生命週期時建立子 session，使用完成後關閉。

```javascript
const client = this.net.session();
try {
    const data = await client.json(url, {headers});
    return {list: data.list};
} finally {
    client.close();
}
```

`await net.ws(url, options)` 是單次 WebSocket 交換，成功 code 為 101，收到首個完整訊息後關閉。持續收訊使用 `net.connect(url, options, callback)`，立即回傳 socket，callback 接收 `(socket, event)`；message 的 content 是文字或 Uint8Array。使用回呼傳入的 socket，每次 open 重新訂閱；reconnect:true 時在 retry 停止心跳並清除殘包，停止或 destroy 時 close／cancel 連線。

## 爬蟲入口

init 收到的 ext 一律是字串。以下範例由來源解析包含 url、detailUrl 的 JSON；網址或其他字串設定保留自己的解析流程。

```javascript
import {Spider} from "catvod";

export default class Source extends Spider {
    init(extend) {
        this.config = JSON.parse(extend);
    }

    async homeContent(filter) {
        const data = await this.net.json(this.config.url);
        return {class: data.categories};
    }

    async detailContent(ids) {
        const list = await this.net.map(ids, async id => {
            const data = await this.net.json(this.config.detailUrl + encodeURIComponent(id));
            return {vod_id: id, vod_name: data.name};
        });
        return {list};
    }
}
```

只接受繼承 `Spider` 的 default class。constructor 保持同步；網路與其他非同步初始化放在 `async init(extend)`，不需初始化時可省略 init。站點鍵由 `this.siteKey` 提供，資源使用 `this.net/local/js/dialog`；輔助模組可從 `catvod` 明確匯入相同資源或便利函式。

| 舊方法 | 現行方法與參數 |
| --- | --- |
| `home(filter)` | `homeContent(filter)` |
| `homeVod()` | `homeVideoContent()` |
| `category(tid, pg, filter, extend)` | `categoryContent(tid, pg, filter, extend)` |
| `detail(id)` | `detailContent(ids)`，收到完整 ID 陣列 |
| `search(key, quick, pg)` | `searchContent(key, quick, pg = "1")` |
| `play(flag, id, flags)` | `playerContent(flag, id, vipFlags)` |
| `live(url)` | `liveContent(url)` |
| `sniffer()` | `manualVideoCheck()` |
| `isVideo(url)` | `isVideoFormat(url)` |

其餘公開入口為 `action(action)`、`proxy(params)`、`danmaku(id, emit)` 與 `destroy()`。action 回傳操作結果，proxy 回傳下節的代理陣列，danmaku 回傳停止函式；它們不是另一組需要改名的舊別名。

搜尋的雙參數入口會由宿主補上字串頁碼 `"1"`，與 Python adapter 一致；顯式傳入的頁碼保持原值。detailContent 收到完整陣列，playerContent 的 vipFlags 也保留完整陣列，空陣列不會省略。categoryContent 的 extend 是物件，參數順序與 Java／Python 相同。

Python 入口目前使用同步 def，Java Spider 入口同步回傳 String／boolean／Object[]；它們沒有自動等待 coroutine 或 Future 的入口協定。JS 的派送層統一 await 同步值、Promise 與 thenable，再依入口交付資料字串、代理陣列或布林值。非同步模型依語言保留，對齊的是方法名稱、參數及完成後的資料語意。

三語言的代理入口均為 `proxy(params)`。Dialog 使用 Java 的 `dialog(options, callback)`、Python 的 `self.dialog(options, callback)`、QuickJS 的 `await this.dialog(options, callback)`；callback 選填。Java init 額外接受 Android Context，JS／Python 的 init 只接收來源設定字串。

init、上述入口、action、proxy、destroy 均可宣告 async 或回傳 Promise，宿主會等待結果。danmaku 可非同步取得停止函式，停止函式本身也可回傳 Promise。這不會讓同步 CPU 計算自動平行執行；呼叫取消與期限仍由 Invocation 管理，constructor 和模組評估也受期限約束。

配置中的 ext 即使原本是 JSON 物件，到 init 仍是 JSON 字串，不額外包成 `{stype, skey, ext}`。categoryContent 的 extend 才是篩選物件，不要對它重複 JSON.parse。類別方法綁定所屬實例，可將 `this.method` 直接交給 map 或事件 callback，並保留相同函式引用；內部一般函式仍遵循 JS 的 this 規則。

資料入口直接回傳物件或陣列，由宿主序列化；舊 JSON 字串改回物件。只有 liveContent 另接受 TXT／M3U 字串。proxy 陣列、manualVideoCheck／isVideoFormat 的布林值不走資料序列化。批次詳情的內部項目方法回傳物件，合併各 list 後再交付。

序列化遵循 JSON.stringify：undefined／function 在物件中省略，在陣列中轉成 null；NaN／Infinity 也轉成 null。BigInt、循環引用及尚未等待的 Promise 不能作為 JSON 結果。Python 不接受 NaN／Infinity，三語言共用資料應使用有效 JSON 值。

錯誤訊息用字串，例如 `{msg: String(error?.message || error)}`；不要直接放入 Error 物件，否則其訊息通常會在 JSON 序列化時遺失。

Dialog 的 callback 收到 `{button, values}`，可回傳更新物件或 Promise；最終回傳 `{button, values}`，取消時為 null。callback 只從第二個參數註冊，options 內的 callback／onAction 欄位不會成為回呼。輸入等待只暫停已讓出執行權的呼叫期限，未 await 的 Dialog 不會停用正在執行 JS 的期限。

不再改寫來源中的 `__JS_SPIDER__` 字串，也不會依舊入口改變 req 的語意。

### 完整 ID 集合

把舊 detail(id) 的單筆請求與解析搬到 `async detailItem(id)`，保留簽名、快取、線路、集數及附加欄位，回傳含 list 的物件。入口處理完整集合：

```javascript
async detailContent(ids) {
    if (!ids.length) return {list: []};
    const responses = await this.net.map(ids, this.detailItem, 4);
    return {...responses[0], list: responses.flatMap(response => response.list)};
}
```

保留輸入順序，不自行去重；空集合不發請求。單筆失敗讓整次呼叫 reject，不捕捉後略過該 ID。範例沿用第一筆的頂層欄位；若來源有批次訊息語意，明確合併必要欄位，不只取 list 而丟失資訊。原 API 若直接支援批次 ID，優先使用其批次接口。

來源原本以空 list 與 msg 回報錯誤時，保留這個錯誤格式並讓整個批次失敗，不交付成功的部分當成完整結果。未上架或沒有可播放內容等合法空結果可與其他詳情合併，但須保留各筆提示，不能只沿用第一筆的 msg。

需要共用登入或依序變更狀態時，以 for...of 逐筆 await，再合併結果。不要用未等待的 forEach(async ...) 或把 ids.map(async ...) 的 Promise 陣列直接放進 list，也不以無上限 Promise.all 取代既有並行限制。

### 非同步與生命週期

純資料組裝保留同步方法；呼叫 net.req／json、js.eval、dialog 或其他 Promise 時，await 或直接 return 該 Promise，並一路修改必要呼叫端。不得在同步 constructor 發出未受等待的初始化請求。

`await this.js.eval(source, {globals, timeout})` 在獨立環境執行短段同步腳本，回傳最後一個運算式的 JSON 值；globals 傳 JSON 資料，timeout 預設 5000 毫秒，不沿用爬蟲的變數、net 或模組。這裡的 await 等待宿主執行完成，腳本結果本身不能是 Promise，也不能以 globals 覆蓋內建 md5X。

只實作來源支援的功能，刪除冗餘覆寫前核對 Spider 預設值。destroy hook 含 Promise 有 5 秒期限，呼叫前網路工作已取消；只釋放自行建立的 Session、reader、連線、計時器或回呼引用，不在 destroy 安排新請求，不關閉共用站點 net。proxy 成功交付的 stream 由 App 接管，不能先關閉再回傳。

## 代理

URL 產生端使用業務參數，不自行組合 do 或 siteKey。

```javascript
const url = this.proxyUrl({url: mediaUrl});
const lanUrl = this.proxyUrl({id: "a+b &=中文"}, false);
```

`proxyUrl(params, local = true)` 只接受字串鍵值，省略 params 或傳入 null 時視為空物件；local 只接受布林。App 加入 do／siteKey 並編碼 query，params 不可覆寫它們。實例方法與從 catvod 匯入的 proxyUrl 使用相同規則，不自行拼接路由。

`proxy(params)` 收到一個扁平的字串鍵值物件，與 Java／Python 一致。HTTP 入口依序合併 query、headers、檔案資訊，後者覆寫同名欄位，do／siteKey 也會傳入；query 已解碼，不重複 decodeURIComponent。

回傳 `[status, mime, body, headers]`，headers 可省略或為 null，額外欄位忽略。status 是 100～599 的整數，MIME 是字串；headers 的值用字串或字串陣列，多值以 `, ` 合併並保留空白。HTTP server 管理 Content-Length／Transfer-Encoding，不轉送來源的這兩個 header。舊 proxy2 物件或 JSON 字串改成此陣列。

```javascript
async proxy(params) {
    const result = await this.net.stream(params.url);
    return [result.code, result.contentType, result.stream, result.headers];
}
```

此方法放在 default 匯出的 Spider 子類別中。stream handle 只能交回目前代理呼叫；自行讀取串流時改用 net.openStream，並在 finally 關閉 reader。

`await net.openStream(url, options)` 的 reader.read(size) 回傳 `Promise<ArrayBuffer>`，EOF 為 null；size 預設 65536，範圍 1～1048576，同一 reader 不並行讀取。自訂正文用 `await net.stream(asyncGenerator())`，每塊輸出 ArrayBuffer／TypedArray，不接受文字或普通陣列，也不傳 HTTP options。上游 reader 在產生器內開啟並以 finally 關閉，不累積整段直播。

非串流 body 可為文字、0～255 整數陣列、ArrayBuffer 或 TypedArray；TypedArray 按其實際 byte 範圍傳遞，文字使用 UTF-8。

```javascript
return [200, "application/octet-stream", new Uint8Array([0, 127, 128, 255])];
```

第五格 Base64 旗標已移除；Base64 與 data URL 字串都當成普通文字，不自動解碼。需要二進位正文時先解碼，再交付 bytes。

## 保留的便利方法與函式庫

| 保留項目 | 保留原因 |
| --- | --- |
| `sha256X(text)` | 同步回傳 SHA-256 hex；WebCrypto digest 是 Promise 與 ArrayBuffer，並非相同呼叫合約 |
| `randomX(size)` | 直接回傳 URL-safe、無 padding 的隨機字串，size 是位元組數；有效範圍為 1..1024，超出範圍仍回傳空字串 |
| `joinUrl(parent, child)` | 保留原 URI 解析語意，避免為改成 new URL 而改變既有來源行為 |
| `getPort()`、`proxyUrl(params, local)` | 取得代理連接埠或目前站點的本機／區域網路代理 URL |
| `md5X/aesX/desX/rsaX` | 保留現有演算法、模式與輸入輸出編碼能力，標準 WebCrypto 不等價涵蓋 |
| `s2t/t2s/openWeb/htmlQuery` | 仍有文字轉換、App 與 HTML 擷取用途 |
| `cheerio.min.js` | 保留 DOM 查詢與操作能力，htmlQuery 不等價涵蓋 |
| `crypto-js.js` | 提供共用雜湊、加解密與二進位編碼能力，來源不必攜帶副本 |
| `gbk.js` | 保留舊站搜尋需要的 GBK URL 編碼；TextDecoder 支援 GBK 解碼，TextEncoder 僅提供 UTF-8 編碼，不能直接取代 |

移除 `cat.js` 與 `similarity.js`：目前使用端沒有引用，前者是多種工具的合併包，後者屬於爬蟲自己的字串比對邏輯。仍使用這兩個模組的外部爬蟲，需改為自行提供相依函式庫，或依實際功能遷移；不能只替換匯入路徑就視為相容。

內建 JS 分為 `js/lib` 的宿主橋接與 `js/vendor` 的工具函式庫。公開 SDK 仍以 `import {Spider} from 'catvod';` 使用；工具庫改從 `assets://js/vendor/` 匯入，原先的 `assets://js/lib/cheerio.min.js`、`crypto-js.js`、`gbk.js` 路徑需同步調整。

紅果的 CryptoJS 匯入改為 `import 'assets://js/vendor/crypto-js.js';`，仍使用其 SHA-512、AES-CBC 與 Base64 能力。這是共用內建函式庫，並非將簽名與加密邏輯改成不同演算法。

new URL、crypto.getRandomValues 與 crypto.subtle.digest 仍可直接使用，但不是要求所有爬蟲遷移便利方法的理由。本次也保留 JAR 注入函式、類別方法的 this、凍結 prototype、彈幕釋放與呼叫取消流程。

## Local 與 TTL 快取

這部分使用既有共用 API，並非本次新增另一套快取。local 保存站點隔離的 JSON 值，提供 get／set／delete，set／delete 不回傳值；不要將 Local 設定當成會自動過期的快取，也不要依賴舊成功／失敗字串或隱含 expiresAt 欄位。

限時資料使用 `await net.cached(key, {ttl, stale, persist}, loader)`；ttl 必填，單位為毫秒，0 不快取，stale 預設 true、persist 預設 false。播放 URL 或短期憑證應依來源期限明確設定，通常使用 `stale: false, persist: false`；失敗應由 loader 拋出，不要偽裝成空的成功結果。舊快取資料不會自動轉換成這個合約。

`peek(key)` 可能回傳過期值；`refresh(key, options, loader)` 立即返回並背景更新；`clearCache(key)` 清單筆，省略 key 清整個站點。這些都位於 net，Session 不支援 persist。

## 驗證

逐一盤點入口及 helper 中的舊入口名稱、全域網路函式、net.http、__jsEvalReturn／__JS_SPIDER__、default 物件／factory、options.async／complete、js2Proxy／proxy2、getProxyUrl／getDanmakuUrl、dialog.show、第五格 Base64 旗標、舊 vendor 路徑與 catvod:host。搜尋命中只是定位，需閱讀函式與必要呼叫端；保留便利函式及合法 JSON.parse 不列為失敗。

| 檢查 | 通過條件 |
| --- | --- |
| 語法與載入 | ES module 語法通過，配套 QuickJS 可載入 default Spider 子類別、helper 與 vendor，init 完成後才呼叫入口 |
| 詳情集合 | 測 `[]`、`["a"]`、`["a", "b"]`、重複 ID 及單筆失敗；核對順序、完整欄位與 reject 傳遞 |
| 參數 | 測 init 的 JSON／網址字串、雙參數搜尋與顯式頁碼、空／多筆 vipFlags、分類 extend 物件 |
| 非同步 | 驗證同步值、Promise 的完成順序，純資料與非同步布林接口、proxy、彈幕停止回呼均符合各自合約 |
| 列表與播放 | 分類／搜尋兩頁、尾頁、無結果與篩選正確；接通列表 ID → 詳情 → 每集播放值 → 播放結果 |
| 網路與資源 | 正文格式、毫秒期限、非 2xx／登入錯誤、Cookie／Session、Local／TTL、Dialog、reader、取消與 destroy 符合來源規則 |
| 代理 | 測空參數、null、字串鍵值、本機／區網 URL、headers、UTF-8 與含 0／128／255 的 bytes；第五格不解碼，串流交接後可讀取並由 App 關閉 |

完整清單才使用 page；外站已分頁就保留當頁，不再切片，有精確總筆數才填 total。記錄配套 App、QuickJS 模組、wrapper／JNI 來源；舊模組缺少 API 時不以相容分支掩蓋配套錯誤。

完成回報列出已修改檔案、保留分支及原因、實際執行的檢查與未測項目。分開說明語法、QuickJS／Android 載入、取樣詳情／播放網址及實際裝置播放；Node.js 或單筆成功不代表每個爬蟲都已全面遷移。
