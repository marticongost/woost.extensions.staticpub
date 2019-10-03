/*-----------------------------------------------------------------------------


@author:        Martí Congost
@contact:       marti.congost@whads.com
@organization:  Whads/Accent SL
@since:         September 2019
-----------------------------------------------------------------------------*/

cocktail.declare("woost.extensions.staticpub.admin.actions");

{
    const requestPublication = function (method, options) {

        const parameters = {
            lang: cocktail.getLanguage(),
            destination: options.destination.id,
            pending_only: options.pending_only ? "true" : "false",
            include_descendants: options.include_descendants ? "true" : "false",
            include_neutral_language: options.include_neutral_language ? "true" : "false",
            language_mode: options.language_mode
        };

        if (options.selection && options.selection.length) {
            parameters.selection = Array.from(options.selection, (item) => typeof(item) == "number" ? item : item.id);
        }

        if (options.language_mode != "all") {
            parameters.language_subset = Array.from(options.language_subset);
        }

        return cocktail.ui.request({
            method,
            url: "/x_staticpub_publication",
            parameters,
            responseType: "json"
        });
    }

    woost.extensions.staticpub.preview = function preview(options) {
        return requestPublication("GET", options);
    }

    woost.extensions.staticpub.publish = function publish(options) {
        return requestPublication("POST", options);
    }
}

woost.extensions.staticpub.admin.actions.PublishAction = class PublishAction extends woost.admin.actions.Action {

    get translationPrefix() {
        return "woost.extensions.staticpub.admin.actions";
    }

    getIconURL(context) {
        return "woost.extensions.staticpub.admin.ui://images/actions/publish.svg";
    }

    matchesModel(model) {
        return model.originalMember.isPublishable;
    }

    invoke(context) {
        cocktail.navigation.extendPath("x-staticpub-publish");
    }
}

woost.extensions.staticpub.admin.actions.BeginPublicationAction = class BeginPublicationAction extends woost.admin.actions.Action {

    get translationPrefix() {
        return "woost.extensions.staticpub.admin.actions";
    }

    getIconURL(context) {
        return "woost.admin.ui://images/actions/accept.svg";
    }

    getState(context) {
        let state = super.getState(context);
        if (state == "visible" && context.state != "ready") {
            state = "disabled";
        }
        return state;
    }

    invoke(context) {
        this.attempt(
            woost.extensions.staticpub.publish(context.publicationOptions)
                .then((xhr) => {
                    cocktail.navigation.extendPath("..", xhr.response.export_id);
                }),
            {successNotice: false}
        );
    }
}

woost.admin.actions.listingToolbar.getEntry("main").add(
    new woost.extensions.staticpub.admin.actions.PublishAction("x-staticpub-publish")
);

woost.admin.actions.editToolbar.getEntry("main").add(
    new woost.extensions.staticpub.admin.actions.PublishAction("x-staticpub-publish")
);

woost.extensions.staticpub.admin.actions.publicationToolbar = new cocktail.ui.ActionSet("x-staticpub-publication-toolbar", {
    entries: [
        new woost.extensions.staticpub.admin.actions.BeginPublicationAction("x-staticpub-begin-publication"),
        new woost.admin.actions.CancelAction("cancel")
    ]
});

