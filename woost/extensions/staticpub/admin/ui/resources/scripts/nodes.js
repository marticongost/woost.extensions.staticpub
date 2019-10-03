/*-----------------------------------------------------------------------------


@author:        Martí Congost
@contact:       marti.congost@whads.com
@organization:  Whads/Accent SL
@since:         September 2019
-----------------------------------------------------------------------------*/

cocktail.declare("woost.extensions.staticpub.admin.nodes");

woost.extensions.staticpub.admin.nodes.PublicationNode = class PublicationNode extends woost.admin.nodes.ItemContainer(woost.admin.nodes.StackNode) {

    get title() {
        return cocktail.ui.translations["woost.extensions.staticpub.admin.nodes.PublicationNode.title"];
    }

    get component() {
        return woost.extensions.staticpub.admin.ui.PublicationView;
    }

    get selection() {
        const stackNode = this.parent.stackNode;
        if (stackNode) {
            const selectable = stackNode.selectable;
            if (selectable) {
                const values = selectable.selectedValues;
                if (values.length) {
                    return values;
                }
            }
        }
        return [];
    }
}

woost.admin.nodes.globalEntries["x-staticpub-publish"] = woost.extensions.staticpub.admin.nodes.PublicationNode;

