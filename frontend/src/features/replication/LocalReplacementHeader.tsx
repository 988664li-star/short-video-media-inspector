export function LocalReplacementHeader() {
  return (
    <header className="local-replacement-header">
      <div className="local-replacement-header__title">
        <span>局部替换</span>
        <div>
          <h2>只换商品，其余爆点保持不变</h2>
          <em className="local-replacement-status">当前可用</em>
        </div>
        <p>导入已授权参考视频，确认商品所在镜头并上传你的商品图；系统按连续片段生成替换视频。</p>
      </div>
      <dl className="local-replacement-method">
        <div><dt>当前范围</dt><dd>单商品替换；动作、机位、节奏与未提及内容尽量保持</dd></div>
        <div><dt>交付方式</dt><dd>连续片段生成、逐段审核</dd></div>
      </dl>
    </header>
  );
}
